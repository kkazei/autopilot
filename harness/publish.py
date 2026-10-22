"""The only caller of publish_post (architecture rule 2), and the only writer of data/approved.jsonl.

publish() trusts nothing its caller decided except the human's approval. Under one cross-process
lock it re-reads approved.jsonl, re-runs the deterministic guardrails on the exact text it will send
with a fresh clock, writes a "pending" row, posts, then writes the "published" row. So:
- two overlapping runs cannot both pass the rate cap (the second one sees the first one's row);
- a post whose outcome is unknown (a crash or a lost write after Bluesky accepted it) still counts
  toward the rate cap and the duplicate check, through its pending row;
- once Bluesky has accepted a post, no bookkeeping failure turns it into a reported failure.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness import guardrails, trace
from harness.fileio import LockTimeout, append_jsonl, file_lock, read_jsonl
from harness.schemas import CRITIQUE_DIMENSIONS, BrandBrief, Critique, Draft, passes_threshold
from mcp_server import bluesky, server

APPROVED_FILE = "approved.jsonl"
PUBLISH_LOCK_FILE = "publish"
PUBLISH_LOCK_TIMEOUT_S = 30.0

Clock = Callable[[], datetime]


class PublishRefused(RuntimeError):
    """A precondition failed; nothing was sent."""


class PublishBlocked(PublishRefused):
    """The publish-time re-check of the guardrails failed; nothing was sent."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class ApprovedLogError(RuntimeError):
    """approved.jsonl has a line we cannot read. It might be a real post, so the rate cap cannot be trusted."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def approved_path() -> Path:
    return trace.data_dir() / APPROVED_FILE


def _lock_path() -> Path:
    return trace.data_dir() / PUBLISH_LOCK_FILE


def live_records() -> list[dict[str, Any]]:
    """Every live post that counts toward the rate cap and the duplicate check, one row per post.

    A post counts when it has a published row, or a pending row with no outcome (it may be live).
    Only an explicit "failed" row (nothing was sent) stops a pending post from counting.
    Rows without a status predate the pending/published split and are published posts.
    Dry-run rows never count. Any unreadable line raises ApprovedLogError: undercounting is not safe.
    """
    path = approved_path()
    with file_lock(path):
        records, invalid = read_jsonl(path)
    if invalid:
        raise ApprovedLogError(f"{path.name} has {invalid} unreadable line(s); refusing to post until it is fixed")
    pending: dict[str, dict[str, Any]] = {}
    done: list[dict[str, Any]] = []
    settled: set[str] = set()
    for r in records:
        if r.get("dry_run"):
            continue
        status = r.get("status", "published")
        key = f"{r.get('run_id')}/{r.get('post_id')}"
        if status == "pending":
            pending[key] = {"text": r.get("text", ""), "posted_at": r.get("started_at"), "status": "pending",
                            "post_id": r.get("post_id")}
        elif status == "failed":
            settled.add(key)
        else:
            settled.add(key)
            done.append(r)
    return done + [p for key, p in pending.items() if key not in settled]


@contextlib.contextmanager
def _harness_env(dry_run: bool) -> Iterator[None]:
    """Grant the harness role for one call only, then restore the environment exactly as it was."""
    keys = (server.ROLE_ENV, server.TOKEN_ENV, server.DRY_RUN_ENV)
    saved = {k: os.environ.get(k) for k in keys}
    os.environ[server.ROLE_ENV] = "harness"
    os.environ[server.TOKEN_ENV] = secrets.token_hex(16)
    if dry_run:
        os.environ[server.DRY_RUN_ENV] = "1"
    else:
        os.environ.pop(server.DRY_RUN_ENV, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def recheck(run_id: str, text: str, brief: BrandBrief, now: datetime, published: list[dict[str, Any]]) -> list[str]:
    """The four deterministic guardrails again, on the exact text about to be sent. Each result is traced."""
    checks = {
        "check_length": guardrails.check_length(text),
        "check_banned": guardrails.check_banned(text, brief.model_dump()),
        "check_rate_cap": guardrails.check_rate_cap(now, published),
        "check_duplicate": guardrails.check_duplicate(text, [r.get("text", "") for r in published]),
    }
    for name, result in checks.items():
        trace.log_event(run_id, "harness", "guardrail", f"publish re-check {name} | {text}",
                        "pass" if result["ok"] else "; ".join(result["reasons"]), ok=result["ok"])
    return [f"{name}: {reason}" for name, r in checks.items() for reason in r["reasons"]]


def publish(run_id: str, draft: Draft, critique: Critique, brief: BrandBrief, *, approved: bool,
            dry_run: bool, min_score: int = 4, clock: Clock = utc_now) -> dict[str, Any]:
    """Publish one draft. `approved` is the human's answer (or True for a dry run with approval off).

    Returns the published record; its "warnings" list names any bookkeeping that failed after the post went out.
    Raises PublishRefused/PublishBlocked when nothing was sent, and lets other errors from the client propagate
    with the pending row left in place, because then the post may or may not be live.
    """
    if not passes_threshold(critique, min_score):
        raise PublishRefused("critique is below the threshold")
    if not approved:
        raise PublishRefused("no human approval")
    # One lock around re-check, pending row, post and result row, so overlapping runs serialize here.
    # Any LockTimeout that escapes happened before the post (the code after the post catches its own).
    try:
        with file_lock(_lock_path(), timeout_s=PUBLISH_LOCK_TIMEOUT_S):
            return _publish_locked(run_id, draft, critique, brief, dry_run=dry_run, now=clock())
    except LockTimeout:
        raise PublishRefused("could not take the publish lock; nothing was sent") from None


def _publish_locked(run_id: str, draft: Draft, critique: Critique, brief: BrandBrief, *,
                    dry_run: bool, now: datetime) -> dict[str, Any]:
    try:
        published = live_records()
    except ApprovedLogError as e:
        raise PublishBlocked([f"approved log: {e}"]) from None
    reasons = recheck(run_id, draft.text, brief, now, published)
    if reasons:
        raise PublishBlocked(reasons)

    base = {"run_id": run_id, "post_id": draft.post_id, "text": draft.text, "dry_run": dry_run}
    # Written before the post: if this fails, nothing has been sent and the error propagates.
    append_jsonl(approved_path(), {**base, "status": "pending", "started_at": now.isoformat()})
    summary_in = f"publish_post | dry_run={dry_run} | {draft.text}"
    try:
        with _harness_env(dry_run):
            posted = server.publish_post(draft.text, draft.post_id)
    except (server.ToolRefused, bluesky.BlueskyAuthError) as e:
        # Refused before anything was sent: settle the pending row so it stops counting.
        with contextlib.suppress(OSError, LockTimeout):
            append_jsonl(approved_path(), {**base, "status": "failed", "reason": f"{type(e).__name__}: {e}"})
        trace.log_event(run_id, "harness", "tool_call", summary_in, f"not sent: {type(e).__name__}: {e}", ok=False)
        raise
    except Exception as e:
        trace.log_event(run_id, "harness", "tool_call", summary_in,
                        f"outcome unknown ({type(e).__name__}: {e}); pending row kept, so it counts", ok=False)
        raise

    # The post is out. From here on nothing may raise: failures become warnings, and the pending row
    # already written keeps the rate cap and duplicate check correct even if the rows below are lost.
    record = {
        **base, "status": "published", "attempt": draft.attempt,
        "scores": {d: getattr(critique, d) for d in CRITIQUE_DIMENSIONS}, "reasons": critique.reasons,
        "uri": posted["uri"], "cid": posted["cid"], "posted_at": posted["posted_at"],
    }
    warnings: list[str] = []
    try:
        append_jsonl(approved_path(), record)
    except (OSError, LockTimeout) as e:
        warnings.append(f"approved.jsonl write failed ({type(e).__name__}); the pending row still counts this post")
    try:
        trace.log_event(run_id, "harness", "tool_call", summary_in, posted["uri"], ok=True)
    except trace.TraceWriteError as e:
        warnings.append(f"trace write failed ({e})")
    return {**record, "warnings": warnings}
