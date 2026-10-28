"""Run trace: every LLM call, tool call, guardrail and decision for one run, in order.

The trace is the evidence the dashboard and the talk rely on, so events are redacted before
they are written, writes are locked and atomic, and a failed write raises TraceWriteError
instead of being skipped: a run with a hole in its trace must not look like a clean run.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from harness.fileio import LockTimeout, atomic_write_text, file_lock
from harness.schemas import TraceEvent

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR_ENV = "AUTOPILOT_DATA_DIR"
SUMMARY_MAX_CHARS = 2000
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

Agent = Literal["planner", "writer", "critic", "analyst", "harness"]
Kind = Literal["llm_call", "tool_call", "guardrail", "decision"]

# Values of these variables are replaced wherever they appear, whatever their format.
SECRET_ENV_VARS = ("OPENROUTER_API_KEY", "BLUESKY_APP_PASSWORD", "AUTOPILOT_PUBLISH_TOKEN", "DATABASE_URL",
                   "AUTOPILOT_BACKEND_SECRET")
_MIN_SECRET_LEN = 8
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-or-[A-Za-z0-9_\-]+"), "[REDACTED:openrouter_key]"),
    # A database URL's password (DATABASE_URL is replaced whole above; this catches any other copy).
    (re.compile(r"(postgres(?:ql)?://[^:/@\s]+):[^@\s]+@"), r"\1:[REDACTED]@"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]+"), "Bearer [REDACTED]"),
    (re.compile(r'("user_id"\s*:\s*)"[^"]*"'), r'\1"[REDACTED]"'),
    # Bluesky app passwords look like xxxx-xxxx-xxxx-xxxx.
    (re.compile(r"\b[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}\b"), "[REDACTED:app_password]"),
)


class TraceWriteError(RuntimeError):
    """The trace could not be written; callers must treat the step as failed."""


def data_dir() -> Path:
    """Read per call so tests and subprocesses can point the whole system at a temp directory."""
    return Path(os.environ.get(DATA_DIR_ENV) or REPO_ROOT / "data")


def run_path(run_id: str) -> Path:
    """run_id becomes a file name, so it is restricted to a safe alphabet (no path traversal)."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    return data_dir() / "runs" / f"{run_id}.json"


def redact(text: str) -> str:
    """Strip known secret values and secret-shaped strings; the trace is committed to git and shown on a public page."""
    for var in SECRET_ENV_VARS:
        value = os.environ.get(var, "")
        if len(value) >= _MIN_SECRET_LEN:
            text = text.replace(value, f"[REDACTED:{var}]")
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _summarize(text: str, truncate: bool) -> str:
    """Redact first, then cut, so a secret straddling the cut is replaced whole and never left half visible.

    The head and the tail are both kept: an llm_call's input ends with the data the model was judging (the
    planned post, the draft), and keeping only the start hid exactly that (ISSUES_LOG 31, run_..._b0e71e).
    """
    text = redact(str(text))
    if truncate and len(text) > SUMMARY_MAX_CHARS:
        head = SUMMARY_MAX_CHARS // 4
        tail = SUMMARY_MAX_CHARS - head
        dropped = len(text) - SUMMARY_MAX_CHARS
        text = f"{text[:head]}...[truncated {dropped} chars]...{text[-tail:]}"
    return text


def _load_events(path: Path) -> list[dict]:
    """A corrupt trace raises rather than being reset: overwriting it would destroy the evidence."""
    if not path.exists():
        return []
    events = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(events, list):
        raise ValueError(f"{path.name} is not a JSON list")
    return events


def start_run() -> str:
    """Create an empty trace file and return its run_id (UTC timestamp plus a random suffix, so parallel runs never collide)."""
    run_id = f"run_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{secrets.token_hex(3)}"
    path = run_path(run_id)
    try:
        with file_lock(path):
            if not path.exists():
                atomic_write_text(path, "[]\n")
    except (OSError, LockTimeout) as e:
        raise TraceWriteError(f"could not create trace for {run_id}: {type(e).__name__}") from e
    return run_id


def log_event(
    run_id: str,
    agent: Agent,
    kind: Kind,
    summary_in: str,
    summary_out: str,
    ok: bool,
    model: str | None = None,
    latency_ms: int | None = None,
    *,
    truncate: bool = True,
    ts: datetime | None = None,
) -> TraceEvent:
    """Append one redacted event. `truncate=False` is for the run summary, which must stay complete.

    `ts` is for an event recorded elsewhere and copied in later (a Hermes tool call): it keeps the time the event
    happened and is placed there in the trace, instead of reading as if it happened at copy time.
    """
    event = TraceEvent(
        ts=ts or datetime.now(timezone.utc),
        run_id=run_id,
        agent=agent,
        kind=kind,
        summary_in=_summarize(summary_in, truncate),
        summary_out=_summarize(summary_out, truncate),
        ok=ok,
        model=model,
        latency_ms=latency_ms,
    )
    path = run_path(run_id)
    try:
        with file_lock(path):
            events = _load_events(path)
            events.insert(len(events) if ts is None else _position(events, event.ts), event.model_dump(mode="json"))
            atomic_write_text(path, json.dumps(events, indent=2, ensure_ascii=False) + "\n")
    except (OSError, LockTimeout, ValueError) as e:
        raise TraceWriteError(f"trace write failed for {run_id}: {type(e).__name__}") from e
    return event


def _position(events: list[dict], ts: datetime) -> int:
    """Index just after the last event at or before `ts`; an unreadable timestamp means "append", never a crash."""
    for i in range(len(events), 0, -1):
        try:
            if datetime.fromisoformat(events[i - 1]["ts"]) <= ts:
                return i
        except (KeyError, TypeError, ValueError):
            return len(events)
    return 0


def read_run(run_id: str) -> list[TraceEvent]:
    try:
        return [TraceEvent.model_validate(e) for e in _load_events(run_path(run_id))]
    except ValidationError as e:
        raise ValueError(f"trace for {run_id} has invalid events") from e


@dataclass
class Step:
    """Filled in by the code inside a `step` block; read when the block exits."""

    summary_out: str = ""
    model: str | None = None
    ok: bool = True


@contextlib.contextmanager
def step(run_id: str, agent: Agent, kind: Kind, summary_in: str) -> Iterator[Step]:
    """Time a step and log it exactly once, so a step that raises still leaves a failed event behind."""
    current = Step()
    started = time.perf_counter()
    try:
        yield current
    except Exception as e:
        log_event(
            run_id, agent, kind, summary_in,
            current.summary_out or f"failed: {type(e).__name__}: {e}",
            ok=False, model=current.model, latency_ms=_elapsed_ms(started),
        )
        raise
    log_event(
        run_id, agent, kind, summary_in, current.summary_out,
        ok=current.ok, model=current.model, latency_ms=_elapsed_ms(started),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
