"""Measure, plan if needed, then write, critique and (only if everything passes) publish the next due post.

    python -m scripts.run_outer --dry-run
    python -m scripts.run_outer
    python -m scripts.run_outer --measure-only
    python -m scripts.run_outer --requeue post_1a2b3c4d

Human approval is on by default; --no-approve is refused unless --dry-run is also set, exactly like run_post.
A dry run reads the real plan state and learnings but writes neither, and makes no Bluesky reads or analyst calls.

Exit codes: 0 done (including "nothing to do yet"), 2 refused by flags or config, 3 escalated, 4 failed,
5 blocked by guardrails, 6 another run is active.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from harness import trace
from harness.env import load_dotenv
from harness.hermes_llm import with_runtime
from harness.llm import LLM, LLMError, OpenRouterLLM
from harness.publish import Clock, utc_now
from harness.schemas import BrandBrief
from loops.outer import EXIT_REFUSED, OuterOptions, requeue_post, run_outer

DEFAULT_ENV_FILE = trace.REPO_ROOT / ".env"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_outer", description=__doc__.split("\n")[0])
    p.add_argument("--dry-run", action="store_true", help="run everything, but publish to a dryrun:// URI and save nothing")
    p.add_argument("--approve", action=argparse.BooleanOptionalAction, default=True,
                   help="ask a human before publishing (default: on; --no-approve needs --dry-run)")
    p.add_argument("--measure-only", action="store_true", help="learn from published posts, then stop")
    p.add_argument("--min-score", type=int, choices=range(1, 6), default=4, metavar="1-5")
    p.add_argument("--requeue", metavar="POST_ID", help="put an escalated post back in the queue (no model calls)")
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
    if clock is None:
        clock = (lambda: now) if now is not None else utc_now
    if args.requeue:
        return requeue_post(args.requeue, _say, clock)
    try:
        brief = BrandBrief.model_validate_json((trace.data_dir() / "brand_brief.json").read_text(encoding="utf-8"))
    except OSError as e:
        _say(f"refused: brand brief could not be read ({type(e).__name__})")
        return EXIT_REFUSED
    except ValidationError as e:
        _say(f"refused: brand brief is invalid ({e.error_count()} errors)")
        return EXIT_REFUSED
    try:
        llm = with_runtime(llm or OpenRouterLLM())
    except LLMError as e:
        _say(f"refused: {e}")
        return EXIT_REFUSED
    opts = OuterOptions(dry_run=args.dry_run, approve=args.approve, measure_only=args.measure_only,
                        min_score=args.min_score)
    return run_outer(llm, brief, opts, input_fn=input_fn, clock=clock, say=_say)


if __name__ == "__main__":
    sys.exit(main())
