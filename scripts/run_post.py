"""Write, critique and (only if everything passes) publish one post on one topic.

    python -m scripts.run_post --topic "Saturday sourdough class" --dry-run
    python -m scripts.run_post --topic "Rye crust" --goal click

Human approval is on by default. --no-approve is refused unless --dry-run is also set, so no live
post goes out without a person saying yes (decision 4.7; revisit deliberately for the Day 2 cron).
The rate cap is checked before any model call, so a post that cannot go out today costs no quota
(decision 4.3).

Exit codes: 0 published, 2 refused by flags or config, 3 escalated, 4 failed, 5 blocked by guardrails.
"""

from __future__ import annotations

import argparse
import contextlib
import secrets
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from harness import guardrails, trace
from harness.env import load_dotenv
from harness.llm import LLM, LLMError, OpenRouterLLM
from harness.publish import (
    ApprovedLogError,
    Clock,
    PublishBlocked,
    PublishRefused,
    live_records,
    publish,
    utc_now,
)
from harness.schemas import BrandBrief, PlannedPost
from loops.inner import run_inner

EXIT_PUBLISHED, EXIT_REFUSED, EXIT_ESCALATED, EXIT_FAILED, EXIT_BLOCKED = 0, 2, 3, 4, 5
DEFAULT_ENV_FILE = trace.REPO_ROOT / ".env"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_post", description=__doc__.split("\n")[0])
    p.add_argument("--topic", required=True)
    p.add_argument("--angle", default="one concrete detail a beginner would notice")
    p.add_argument("--goal", choices=("awareness", "engagement", "click"), default="engagement")
    p.add_argument("--dry-run", action="store_true", help="run everything, but publish to a dryrun:// URI")
    p.add_argument("--approve", action=argparse.BooleanOptionalAction, default=True,
                   help="ask a human before publishing (default: on; --no-approve needs --dry-run)")
    p.add_argument("--min-score", type=int, choices=range(1, 6), default=4, metavar="1-5")
    return p.parse_args(argv)


def _say(message: str) -> None:
    print(trace.redact(message), flush=True)


def main(argv: Sequence[str] | None = None, *, llm: LLM | None = None,
         input_fn: Callable[[str], str] = input, now: datetime | None = None,
         clock: Clock | None = None, env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    """Tests inject `llm`, `input_fn` and `now` or `clock`, and pass env_file=None so the real .env never loads."""
    args = parse_args(argv)
    if not args.approve and not args.dry_run:
        _say("refused: --no-approve is only allowed together with --dry-run")
        return EXIT_REFUSED
    if env_file is not None:
        load_dotenv(env_file)
    # Tests pin the clock; a real run reads it again at publish time, after the approval wait.
    if clock is None:
        clock = (lambda: now) if now is not None else utc_now
    now = clock()

    # Config problems are refused before a trace exists, so they never leave an empty run behind.
    try:
        brief = BrandBrief.model_validate_json((trace.data_dir() / "brand_brief.json").read_text(encoding="utf-8"))
    except OSError as e:
        _say(f"refused: brand brief could not be read ({type(e).__name__})")
        return EXIT_REFUSED
    except ValidationError as e:
        _say(f"refused: brand brief is invalid ({e.error_count()} errors)")
        return EXIT_REFUSED
    try:
        llm = llm or OpenRouterLLM()
    except LLMError as e:
        _say(f"refused: {e}")
        return EXIT_REFUSED

    run_id = trace.start_run()
    trace.log_event(run_id, "harness", "decision", f"run_post | topic={args.topic!r} goal={args.goal}",
                    f"start: dry_run={args.dry_run} approval={args.approve} min_score={args.min_score}", ok=True)
    _say(f"run {run_id}  (dry_run={args.dry_run}, approval={args.approve})")

    try:
        published = live_records()
    except ApprovedLogError as e:
        trace.log_event(run_id, "harness", "decision", "approved log pre-check", str(e), ok=False)
        _say(f"blocked before writing: {e}")
        return EXIT_BLOCKED
    cap = guardrails.check_rate_cap(now, published)
    if not cap["ok"]:
        trace.log_event(run_id, "harness", "decision", "rate cap pre-check", "; ".join(cap["reasons"]), ok=False)
        _say("blocked before writing: " + "; ".join(cap["reasons"]))
        return EXIT_BLOCKED

    # The post's day is the UTC date, like every other timestamp the harness writes.
    planned = PlannedPost(id=f"post_{secrets.token_hex(4)}", day=now.astimezone(timezone.utc).date(),
                          topic=args.topic, angle=args.angle, goal=args.goal)
    result = run_inner(llm, run_id, planned, brief, min_score=args.min_score)
    for i, a in enumerate(result.attempts, 1):
        c = a.critique
        _say(f"\nattempt {i}: {a.draft.text}\n  scores voice={c.voice} clarity={c.clarity} cta={c.cta} "
             f"policy_risk={c.policy_risk}\n" + "\n".join(f"  {k}: {v}" for k, v in c.reasons.items()))
    if result.status == "failed":
        _say(f"\nfailed: {result.error}")
        return EXIT_FAILED
    if result.status == "escalated":
        cause = f" (stopped by a model error: {result.error})" if result.error else ""
        _say(f"\nescalated after {len(result.attempts)} attempts{cause}: needs human review; nothing published")
        return EXIT_ESCALATED

    final = result.final
    assert final is not None  # "passed" always has an attempt
    gate = guardrails.run_all(final.draft.text, brief.model_dump(), run_id=run_id, now=now,
                              published_log=published, recent_texts=[r["text"] for r in published],
                              approval_enabled=args.approve, input_fn=input_fn)
    if not gate["ok"]:
        trace.log_event(run_id, "harness", "decision", f"publish {planned.id}",
                        "blocked: " + "; ".join(gate["reasons"]), ok=False)
        _say("\nblocked: " + "; ".join(gate["reasons"]))
        return EXIT_BLOCKED

    try:
        # publish() re-checks everything itself under its lock; the only thing it takes from here is the approval.
        record = publish(run_id, final.draft, final.critique, brief, approved=True, dry_run=args.dry_run,
                         min_score=args.min_score, clock=clock)
    except PublishBlocked as e:
        trace.log_event(run_id, "harness", "decision", f"publish {planned.id}", f"blocked at publish: {e}", ok=False)
        _say(f"\nblocked at publish time: {e}")
        return EXIT_BLOCKED
    except PublishRefused as e:
        trace.log_event(run_id, "harness", "decision", f"publish {planned.id}", f"refused: {e}", ok=False)
        _say(f"\nrefused: {e}")
        return EXIT_REFUSED
    except Exception as e:  # noqa: BLE001 - any client error here may mean the post is live; report, never retry
        with contextlib.suppress(trace.TraceWriteError):
            trace.log_event(run_id, "harness", "decision", f"publish {planned.id}",
                            f"failed, outcome unknown: {type(e).__name__}: {e}", ok=False)
        _say(f"\npublish failed and the outcome is unknown ({type(e).__name__}: {e}). Check the account before "
             "retrying; the pending row keeps counting toward the rate cap.")
        return EXIT_FAILED
    # The post is out: bookkeeping problems are reported, never turned into a failure.
    with contextlib.suppress(trace.TraceWriteError):
        trace.log_event(run_id, "harness", "decision", f"publish {planned.id}", f"published: {record['uri']}",
                        ok=True)
    for warning in record["warnings"]:
        _say(f"warning: {warning}")
    _say(f"\npublished: {record['uri']}\ntrace: {trace.run_path(run_id)}")
    return EXIT_PUBLISHED


if __name__ == "__main__":
    sys.exit(main())
