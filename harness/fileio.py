"""File primitives shared by the trace, the MCP server and (later) the quota file.

Several processes write under data/ at once (the harness and each MCP server subprocess), so
writes take a cross-process lock and land atomically: a reader never sees a half-written file.
Standard library only, so Windows and CI take the same code path.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

LOCK_TIMEOUT_S = 10.0
STALE_LOCK_S = 60.0
_POLL_S = 0.02
_REPLACE_RETRIES = 20


class LockTimeout(TimeoutError):
    """Raised instead of writing unlocked: callers fail closed rather than risk a torn file."""


def _break_if_stale(lock: Path) -> None:
    """A lock that outlives any real write belongs to a crashed process; holding it forever would wedge every run."""
    with contextlib.suppress(OSError):
        if time.time() - lock.stat().st_mtime > STALE_LOCK_S:
            lock.unlink()


@contextlib.contextmanager
def file_lock(path: Path, timeout_s: float = LOCK_TIMEOUT_S) -> Iterator[None]:
    """Lock `path` via an O_EXCL sibling file, which behaves the same on Windows and POSIX (unlike fcntl/msvcrt)."""
    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):
            # Windows reports PermissionError while another process is mid-delete of the lock.
            _break_if_stale(lock)
            if time.monotonic() >= deadline:
                raise LockTimeout(f"could not lock {path.name} within {timeout_s}s") from None
            time.sleep(_POLL_S)
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(lock)


def atomic_write_text(path: Path, text: str) -> None:
    """Write to a temp file in the same directory, then rename over the target, so readers see old or new, never partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(_REPLACE_RETRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                # Windows refuses the rename while a reader briefly holds the target open.
                if attempt == _REPLACE_RETRIES - 1:
                    raise
                time.sleep(_POLL_S)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """One locked append per record, so lines from concurrent writers never interleave."""
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with file_lock(path):
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line)


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Return (records, invalid_line_count); counting bad lines lets callers report them instead of crashing on them."""
    if not path.exists():
        return [], 0
    records: list[dict[str, Any]] = []
    invalid = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            invalid += 1
    return records, invalid
