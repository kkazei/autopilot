"""How many model requests a run may still make today, counted from the traces already on disk.

OpenRouter's free tier allows about 50 requests a day (unconfirmed for this account, ISSUES_LOG 18). Counting
`llm_call` events is conservative: it includes every failed attempt (429s too), which may not match how
OpenRouter counts, but it never undercounts what this repo sent.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from harness import trace

DAILY_REQUEST_LIMIT = 50
RUN_REQUEST_CAP = 16
MEASURE_REQUEST_CAP = 4
WINDOW = timedelta(hours=24)


def llm_calls_since(since: datetime, runs_dir: Path | None = None) -> tuple[int, int]:
    """Return (llm_call events at or after `since`, trace files that could not be read).

    Read-only. An unreadable trace is counted and reported, not skipped silently, so the caller can say
    its number may be low.
    """
    runs_dir = runs_dir or trace.data_dir() / "runs"
    used = unreadable = 0
    for path in runs_dir.glob("run_*.json"):
        try:
            events = json.loads(path.read_text(encoding="utf-8"))
            used += sum(1 for e in events
                        if e["kind"] == "llm_call" and datetime.fromisoformat(e["ts"]) >= since)
        except (OSError, ValueError, KeyError, TypeError):
            unreadable += 1
    return used, unreadable


def run_cap(now: datetime, runs_dir: Path | None = None) -> tuple[int, int, int]:
    """Return (this run's attempt cap, attempts used in the last 24 hours, unreadable trace files)."""
    used, unreadable = llm_calls_since(now - WINDOW, runs_dir)
    return max(0, min(RUN_REQUEST_CAP, DAILY_REQUEST_LIMIT - used)), used, unreadable
