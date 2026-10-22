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
import secrets
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from pathlib import Path

from harness import guardrails, trace
from harness.env import load_dotenv
from harness.llm import LLM, LLMError, OpenRouterLLM
from harness.publish import live_records, publish
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
         env_file: Path | None = DEFAULT_ENV_FILE) -> int:
    """Tests inject `llm`, `input_fn` and `now`, and pass env_file=None so the real .env never loads."""
    args = parse_args(argv)
    if not args.approve and not args.dry_run:
        _say("refused: --no-approve is only allowed together with --dry-run")
        return EXIT_REFUSED
    if env_file is not None:
        load_dotenv(env_file)
    now = now or datetime.now(timezone.utc)

    run_id = trace.start_run()
    trace.log_event(run_id, "harness", "decision", f"run_post | topic={args.topic!r} goal={args.goal}",
                    f"start: dry_run={args.dry_run} approval={args.approve} min_score={args.min_score}", ok=True)
    _say(f"run {run_id}  (dry_run={args.dry_run}, approval={args.approve})")

    published = live_records()
    cap = guardrails.check_rate_cap(now, published)
    if not cap["ok"]:
        trace.log_event(run_id, "harness", "decision", "rate cap pre-check", "; ".join(cap["reasons"]), ok=False)
        _say("blocked before writing: " + "; ".join(cap["reasons"]))
        return EXIT_BLOCKED

    brief = BrandBrief.model_validate_json((trace.data_dir() / "brand_brief.json").read_text(encoding="utf-8"))
    planned = PlannedPost(id=f"post_{secrets.token_hex(4)}", day=date.today(), topic=args.topic,
                          angle=args.angle, goal=args.goal)
    try:
        llm = llm or OpenRouterLLM()
    except LLMError as e:
        _say(f"refused: {e}")
        return EXIT_REFUSED

    result = run_inner(llm, run_id, planned, brief, min_score=args.min_score)
    for i, a in enumerate(result.attempts, 1):
        c = a.critique
        _say(f"\nattempt {i}: {a.draft.text}\n  scores voice={c.voice} clarity={c.clarity} cta={c.cta} "
             f"policy_risk={c.policy_risk}\n" + "\n".join(f"  {k}: {v}" for k, v in c.reasons.items()))
    if result.status == "failed":
        _say(f"\nfailed: {result.error}")
        return EXIT_FAILED
    if result.status == "escalated":
        _say(f"\nescalated after {len(result.attempts)} attempts: needs human review; nothing published")
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

    record = publish(run_id, final.draft, final.critique, gate, dry_run=args.dry_run, min_score=args.min_score)
    trace.log_event(run_id, "harness", "decision", f"publish {planned.id}", f"published: {record['uri']}", ok=True)
    _say(f"\npublished: {record['uri']}\ntrace: {trace.run_path(run_id)}")
    return EXIT_PUBLISHED


if __name__ == "__main__":
    sys.exit(main())
