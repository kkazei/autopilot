"""Postgres is the source of truth for the hosted app, while the harness keeps working on plain files.

A hosted run (the web backend or the scheduled cron) takes one database lock, pulls the current state into an
empty working folder, runs the unchanged harness against that folder, and pushes the result back. Keeping the
harness on files means the publish lock, the rate cap and the MCP server subprocesses behave exactly as they do
locally (architecture rule 2), and the CLI still runs with no database at all.

The database lock stands in for the file locks across machines: the cron and the web backend never share a disk,
so without it two hosted runs could both pass the rate cap. The logs are append-only, so a push that would shorten
or rewrite one is refused rather than allowed to forget a post that went out.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from harness import trace
from harness.fileio import read_jsonl

DOCS = ("brand_brief.json", "plan_state.json")
LOGS = ("approved.jsonl", "learnings.jsonl", "measurements.jsonl")
# Longer than quota.WINDOW plus the longest run, so the pulled traces always cover the 24-hour request count.
RUN_WINDOW = timedelta(hours=48)
LIVE_PUSH_S = 3.0


class StoreBusy(RuntimeError):
    """Another hosted run holds the lock; nothing was pulled or changed."""


class SyncError(RuntimeError):
    """Some state could not be saved to the database; the message names each part, never a value."""


class Store(Protocol):
    def try_lock(self) -> bool: ...
    def unlock(self) -> None: ...
    def get_doc(self, name: str) -> Any | None: ...
    def put_doc(self, name: str, data: Any) -> None: ...
    def get_log(self, name: str) -> list[dict[str, Any]]: ...
    def append_log(self, name: str, start: int, records: list[dict[str, Any]]) -> None: ...
    def runs_since(self, since: datetime) -> dict[str, list[dict[str, Any]]]: ...
    def put_run(self, run_id: str, started_at: datetime, events: list[dict[str, Any]]) -> None: ...


@dataclass
class PushReport:
    docs: list[str] = field(default_factory=list)
    appended: dict[str, int] = field(default_factory=dict)
    runs: int = 0


def run_started_at(run_id: str, events: list[dict[str, Any]]) -> datetime:
    """The id carries the start time (trace.start_run); the first event is the fallback for older names."""
    with contextlib.suppress(ValueError):
        return datetime.strptime(run_id[4:19], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    with contextlib.suppress(IndexError, KeyError, TypeError, ValueError):
        return datetime.fromisoformat(events[0]["ts"])
    return datetime.now(timezone.utc)


def pull(store: Store, work_dir: Path, now: datetime) -> None:
    """Write the database state into `work_dir` in the exact layout the harness reads from data/."""
    work_dir.mkdir(parents=True, exist_ok=True)
    for name in DOCS:
        data = store.get_doc(name)
        if data is not None:
            (work_dir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name in LOGS:
        lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in store.get_log(name)]
        (work_dir / name).write_text("".join(lines), encoding="utf-8")
    runs_dir = work_dir / "runs"
    runs_dir.mkdir(exist_ok=True)
    for run_id, events in store.runs_since(now - RUN_WINDOW).items():
        if not trace.RUN_ID_RE.match(run_id):
            raise SyncError(f"database holds an invalid run id: {run_id!r}")
        (runs_dir / f"{run_id}.json").write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")


def push_runs(store: Store, work_dir: Path, seen: dict[str, tuple[int, int]]) -> int:
    """Upsert every trace file that changed since `seen` (updated in place); returns how many were sent."""
    sent = 0
    for path in sorted((work_dir / "runs").glob("run_*.json")):
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if seen.get(path.name) == stamp:
            continue
        events = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(events, list):
            raise SyncError(f"{path.name} is not a JSON list")
        store.put_run(path.stem, run_started_at(path.stem, events), events)
        seen[path.name] = stamp
        sent += 1
    return sent


def _push_log(store: Store, work_dir: Path, name: str) -> int:
    path = work_dir / name
    records, invalid = read_jsonl(path)
    if invalid:
        # Dropping an unreadable approved.jsonl line could hide a live post from the rate cap.
        raise SyncError(f"{name} has {invalid} unreadable line(s)")
    stored = store.get_log(name)
    if records[:len(stored)] != stored:
        raise SyncError(f"{name} no longer starts with the {len(stored)} record(s) already in the database")
    new = records[len(stored):]
    if new:
        store.append_log(name, len(stored), new)
    return len(new)


def push(store: Store, work_dir: Path) -> PushReport:
    """Save everything in `work_dir`; every part is attempted, so one bad file never costs the run its trace."""
    report = PushReport()
    errors: list[str] = []
    try:
        report.runs = push_runs(store, work_dir, {})
    except (OSError, ValueError, SyncError) as e:
        errors.append(f"runs: {e}")
    for name in LOGS:
        try:
            report.appended[name] = _push_log(store, work_dir, name)
        except (OSError, SyncError) as e:
            errors.append(str(e))
    for name in DOCS:
        path = work_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if store.get_doc(name) != data:
                store.put_doc(name, data)
                report.docs.append(name)
        except (OSError, ValueError) as e:
            errors.append(f"{name}: {type(e).__name__}")
    if errors:
        raise SyncError("; ".join(errors))
    return report


class LivePusher:
    """Sends trace files while a run is going, so the web app can show progress before the run ends.

    Best effort: a failed live push is counted and the final push() still decides whether the run was saved.
    """

    def __init__(self, store: Store, work_dir: Path, interval_s: float = LIVE_PUSH_S) -> None:
        self._store, self._work_dir, self._interval_s = store, work_dir, interval_s
        self._seen: dict[str, tuple[int, int]] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="autopilot-live-push", daemon=True)
        self.failures = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=30)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval_s):
            try:
                push_runs(self._store, self._work_dir, self._seen)
            except Exception:  # noqa: BLE001 - live progress must never take the run down
                self.failures += 1


@contextlib.contextmanager
def hosted_data_dir(store: Store, work_dir: Path, *, now: datetime | None = None,
                    live_interval_s: float = LIVE_PUSH_S) -> Iterator[Path]:
    """Hold the lock, pull, point the harness at `work_dir`, then always push (a failed run still leaves its trace)."""
    if not store.try_lock():
        raise StoreBusy("another hosted run is active")
    try:
        pull(store, work_dir, now or datetime.now(timezone.utc))
        saved = os.environ.get(trace.DATA_DIR_ENV)
        os.environ[trace.DATA_DIR_ENV] = str(work_dir)
        pusher = LivePusher(store, work_dir, live_interval_s)
        pusher.start()
        try:
            yield work_dir
        finally:
            pusher.stop()
            if saved is None:
                os.environ.pop(trace.DATA_DIR_ENV, None)
            else:
                os.environ[trace.DATA_DIR_ENV] = saved
            push(store, work_dir)
    finally:
        store.unlock()
