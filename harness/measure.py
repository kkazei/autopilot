"""Measure published posts and save a learning for each: deterministic orchestration, so it lives in harness/.

The harness decides which posts to read, reads the counts itself and validates them; the analyst is only a
function it calls when there is enough signal to say something. Nothing here retries or sleeps: a failed
read is traced and the run moves on, because the next scheduled run is the retry.

A post whose only learning is "not enough data" is read again on later runs: engagement can arrive days after the
first read. If it is still under the threshold nothing is written (the old line stands, and the file does not
fill with identical lines); once it crosses the threshold the analyst's learning is appended and the post is done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from agents import analyst
from harness import trace
from harness.fileio import LockTimeout, append_jsonl, read_jsonl
from harness.llm import LLM, Budget, LLMBudgetExceeded, LLMError
from harness.publish import fetch_metrics, live_records, record_learning
from harness.schemas import Learning
from mcp_server import bluesky
from mcp_server.server import ToolRefused

MIN_POST_AGE = timedelta(hours=2)
MIN_ENGAGEMENT = 2
MAX_NOT_FOUND = 3
METRIC_KEYS = ("likes", "reposts", "replies")
# The exact sentence marks a learning that carries no signal, so the schema needs no extra field.
NOT_ENOUGH_DATA_INSIGHT = ("Not enough data yet: under 2 likes, reposts and replies in total, "
                           "so this post is not engagement evidence.")
LEARNINGS_FILE = "learnings.jsonl"
MEASUREMENTS_FILE = "measurements.jsonl"


@dataclass
class MeasureResult:
    learned: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # human-readable reasons, for the run summary
    stopped: str | None = None  # why measuring ended early, if it did


def _parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return ts if ts.tzinfo is not None else None


def valid_metrics(raw: Any) -> dict[str, int] | None:
    """Exactly the three counts as non-negative ints; anything else is a broken read, not a zero."""
    if not isinstance(raw, dict):
        return None
    counts = {k: raw.get(k) for k in METRIC_KEYS}
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in counts.values()):
        return None
    return {k: int(v) for k, v in counts.items()}


def measure_posts(llm: LLM, run_id: str, now: datetime, *, dry_run: bool, budget: Budget | None = None) -> MeasureResult:
    """Learn from every old-enough published post that has no learning yet. Raises ApprovedLogError if the log is unreadable."""
    result = MeasureResult()
    published = live_records()
    learnings, invalid = read_jsonl(trace.data_dir() / LEARNINGS_FILE)
    if invalid:
        # The "already has a learning" check cannot be trusted, so writing could duplicate one.
        result.stopped = f"learnings.jsonl has {invalid} unreadable line(s); no learnings written this run"
        trace.log_event(run_id, "harness", "decision", "measure", f"warning: {result.stopped}", ok=False)
        return result
    # "Learned" means a learning with signal. A post that only has the fixed "not enough data" line is still open.
    learned_ids = {r.get("post_id") for r in learnings if r.get("insight") != NOT_ENOUGH_DATA_INSIGHT}
    thin_ids = {r.get("post_id") for r in learnings} - learned_ids
    outcomes, _ = read_jsonl(trace.data_dir() / MEASUREMENTS_FILE)
    not_found: dict[str, int] = {}
    for o in outcomes:
        if o.get("outcome") == "not_found":
            not_found[o.get("post_id", "")] = not_found.get(o.get("post_id", ""), 0) + 1

    todo: list[dict[str, Any]] = []
    for r in sorted(published, key=lambda r: str(r.get("posted_at"))):
        post_id, uri = str(r.get("post_id")), str(r.get("uri", ""))
        if r.get("status", "published") != "published" or not uri.startswith("at://") or post_id in learned_ids:
            continue
        posted_at = _parse_ts(r.get("posted_at"))
        if posted_at is None:
            result.skipped.append(f"{post_id}: unreadable posted_at")
        elif now - posted_at < MIN_POST_AGE:
            result.skipped.append(f"{post_id}: not yet measurable (under {MIN_POST_AGE})")
        elif not_found.get(post_id, 0) >= MAX_NOT_FOUND:
            result.skipped.append(f"{post_id}: given up after {MAX_NOT_FOUND} not-found reads")
        else:
            todo.append(r)
    trace.log_event(run_id, "harness", "decision", "measure candidates",
                    f"{len(todo)} to measure; " + ("; ".join(result.skipped) or "none skipped"), ok=True)
    if dry_run:
        trace.log_event(run_id, "harness", "decision", "measure",
                        "would measure: " + (", ".join(str(r["post_id"]) for r in todo) or "nothing"), ok=True)
        return result

    for r in todo:
        post_id = str(r["post_id"])
        try:
            raw = fetch_metrics(run_id, r["uri"])
        except bluesky.BlueskyNotFound:
            # Possibly deleted, possibly not indexed: either way no learning, and a few strikes end the checking.
            append_jsonl(trace.data_dir() / MEASUREMENTS_FILE,
                         {"run_id": run_id, "post_id": post_id, "outcome": "not_found", "at": now.isoformat()})
            trace.log_event(run_id, "harness", "decision", f"measure {post_id}",
                            "post not found: possibly deleted; no learning", ok=False)
            continue
        except (KeyError, TypeError, ValueError):
            raw = None  # the tool could not turn the reply into three counts: handled as a bad shape below
        except Exception as e:  # noqa: BLE001 - any other read failure (auth, rate limit, network) ends measuring
            result.stopped = f"metrics read failed ({type(e).__name__}); measuring stopped"
            trace.log_event(run_id, "harness", "decision", f"measure {post_id}", f"warning: {result.stopped}", ok=False)
            return result
        metrics = valid_metrics(raw)
        if metrics is None:
            result.skipped.append(f"{post_id}: metrics had an unexpected shape")
            trace.log_event(run_id, "harness", "decision", f"measure {post_id}",
                            "error: metrics missing likes, reposts or replies as non-negative integers; no learning",
                            ok=False)
            continue
        enough = sum(metrics.values()) >= MIN_ENGAGEMENT
        if not enough and post_id in thin_ids:
            # Its "not enough data" line already says this; writing it again on every run would only pad the file.
            result.skipped.append(f"{post_id}: still under {MIN_ENGAGEMENT} engagements; the earlier learning stands")
            continue
        try:
            if not enough:
                learning = Learning(run_id=run_id, post_id=post_id, metrics=metrics,
                                    insight=NOT_ENOUGH_DATA_INSIGHT)  # no model call, no quota
            else:
                learning = analyst.analyze(llm, run_id, post_id, str(r.get("text", "")), metrics, budget)
            record_learning(run_id, learning)
        except LLMBudgetExceeded as e:
            result.stopped = f"request budget used up ({e}); measuring stopped"
            trace.log_event(run_id, "harness", "decision", f"measure {post_id}", f"stop: {result.stopped}", ok=False)
            return result
        except (LLMError, ToolRefused, LockTimeout, OSError) as e:
            result.stopped = f"could not learn from {post_id} ({type(e).__name__}); measuring stopped"
            trace.log_event(run_id, "harness", "decision", f"measure {post_id}", f"warning: {result.stopped}", ok=False)
            return result
        result.learned.append(post_id)
    return result
