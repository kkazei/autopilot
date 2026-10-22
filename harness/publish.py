"""The only caller of publish_post (architecture rule 2), and the writer of data/approved.jsonl.

publish() re-checks its preconditions instead of trusting its caller: the critique must pass the
threshold on its scores and the guardrail result must be ok (approval included). The harness role
and its token exist in the environment only for the duration of the one call.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from harness import trace
from harness.fileio import append_jsonl, read_jsonl
from harness.schemas import CRITIQUE_DIMENSIONS, Critique, Draft, passes_threshold
from mcp_server import server

APPROVED_FILE = "approved.jsonl"


class PublishRefused(RuntimeError):
    """A precondition failed; nothing was sent."""


def approved_path() -> Path:
    return trace.data_dir() / APPROVED_FILE


def live_records() -> list[dict[str, Any]]:
    """Dry-run rows are kept for the record but never count toward the rate cap or the duplicate check."""
    records, _invalid = read_jsonl(approved_path())
    return [r for r in records if not r.get("dry_run")]


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


def publish(run_id: str, draft: Draft, critique: Critique, gate: Mapping[str, Any], *,
            dry_run: bool, min_score: int = 4) -> dict[str, Any]:
    if not passes_threshold(critique, min_score):
        raise PublishRefused("critique is below the threshold")
    if gate.get("ok") is not True:
        raise PublishRefused(f"guardrails did not pass: {gate.get('reasons')}")
    with trace.step(run_id, "harness", "tool_call", f"publish_post | dry_run={dry_run} | {draft.text}") as s:
        with _harness_env(dry_run):
            posted = server.publish_post(draft.text, draft.post_id)
        s.summary_out = posted["uri"]
    record = {
        "run_id": run_id, "post_id": draft.post_id, "attempt": draft.attempt, "text": draft.text,
        "scores": {d: getattr(critique, d) for d in CRITIQUE_DIMENSIONS}, "reasons": critique.reasons,
        "uri": posted["uri"], "cid": posted["cid"], "posted_at": posted["posted_at"], "dry_run": dry_run,
    }
    append_jsonl(approved_path(), record)
    return record
