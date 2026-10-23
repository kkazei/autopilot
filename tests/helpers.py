"""Shared fixtures and builders for the outer-loop tests (measure, planner, plan state, outer run)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from harness import trace
from harness.fileio import append_jsonl
from harness.publish import approved_path
from mcp_server import server

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
REASONS = {d: f"{d} is fine." for d in ("voice", "clarity", "cta", "policy_risk")}
GOOD_TEXT = json.dumps({"text": "Saturday's class starts with flour on your hands. Save a seat at the link."})


def scores(n: int = 5) -> str:
    return json.dumps({"voice": n, "clarity": n, "cta": n, "policy_risk": n, "reasons": REASONS})


def week_json(days: tuple[str, ...] = ("2026-10-23", "2026-10-25", "2026-10-27"), rationale: str = "A steady week.") -> str:
    posts = [{"id": f"p{i}", "day": d, "topic": f"Topic {i}", "angle": f"Angle {i}", "goal": "click"}
             for i, d in enumerate(days, 1)]
    return json.dumps({"posts": posts, "rationale": rationale})


def insight_json(text: str = "Short posts about the class got replies.") -> str:
    return json.dumps({"insight": text})


@pytest.fixture
def data(tmp_path, monkeypatch) -> Path:
    shutil.copy(REPO_ROOT / "data" / "brand_brief.json", tmp_path / "brand_brief.json")
    monkeypatch.setenv(trace.DATA_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(server.CALL_LOG_ENV, str(tmp_path / "calls.jsonl"))
    for var in (server.ROLE_ENV, server.TOKEN_ENV, server.DRY_RUN_ENV):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def add_published(post_id: str, age: timedelta = timedelta(hours=5), *, uri: str | None = None,
                  status: str = "published", dry_run: bool = False, text: str | None = None) -> dict:
    row = {"run_id": "run_old", "post_id": post_id, "text": text or f"An old post called {post_id}, about rye.",
           "dry_run": dry_run, "status": status, "attempt": 1}
    if status == "published":
        row.update(uri=uri or f"at://did:plc:test/app.bsky.feed.post/{post_id}", cid="c",
                   posted_at=(NOW - age).isoformat())
    else:
        row["started_at"] = (NOW - age).isoformat()
    append_jsonl(approved_path(), row)
    return row


def add_learning(post_id: str, insight: str = "Class posts get replies.", metrics: dict | None = None) -> None:
    append_jsonl(trace.data_dir() / "learnings.jsonl", {
        "run_id": "run_old", "post_id": post_id, "metrics": metrics or {"likes": 2, "reposts": 0, "replies": 1},
        "insight": insight, "saved_at": NOW.isoformat()})
