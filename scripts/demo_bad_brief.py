"""Replay the planted-bad-brief demo with scripted models: no network, no quota, nothing written to data/.

    python -m scripts.demo_bad_brief

The brief in docs/demo/bad_brief.json tells the writer to be pushy and to promise results, while its own
banned list forbids that wording. The models here are scripted (MockLLM), so this shows how the harness reacts,
not what a real free model would write:

  attempt 1  a pushy draft: the critic scores it low, so the writer must revise (a critic rejection)
  attempt 2  a draft that follows the brief: a lenient critic gives it 5/5, and the harness still blocks it
             because it contains a banned phrase (a guardrail block). Nobody is asked to approve it.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from harness import trace
from harness.llm import MockLLM
from mcp_server import server
from scripts import run_post

BRIEF = trace.REPO_ROOT / "docs" / "demo" / "bad_brief.json"
PUSHY = "Only 3 seats left!!! Book TODAY or you lose your spot. https://example.com/bramblewick/classes"
PROMISE = "Results guaranteed: bake perfect bread after one Saturday class. https://example.com/bramblewick/classes"


def _scores(voice: int, clarity: int, cta: int, policy: int, why: str) -> str:
    return json.dumps({"voice": voice, "clarity": clarity, "cta": cta, "policy_risk": policy,
                       "reasons": {"voice": why, "clarity": why, "cta": why, "policy_risk": why}})


def script() -> list[str]:
    """Writer and critic replies in call order: writer, critic, writer, critic."""
    return [json.dumps({"text": PUSHY}),
            _scores(1, 3, 3, 2, "Shouting and a pressure tactic; not warm or unhurried."),
            json.dumps({"text": PROMISE}),
            _scores(5, 5, 5, 5, "Clear and confident.")]  # the critic misses it: the harness must not


def run_demo(work_dir: Path) -> tuple[int, list]:
    """Run once in `work_dir` and return (exit code, trace events). Environment changes are undone afterwards."""
    shutil.copy(BRIEF, work_dir / "brand_brief.json")
    keys = (trace.DATA_DIR_ENV, server.CALL_LOG_ENV, "AUTOPILOT_WRITER_RUNTIME")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ[trace.DATA_DIR_ENV] = str(work_dir)
    os.environ[server.CALL_LOG_ENV] = str(work_dir / "calls.jsonl")
    os.environ["AUTOPILOT_WRITER_RUNTIME"] = "direct"

    def never_asked(prompt: str) -> str:
        raise AssertionError("a blocked post must never reach the approval prompt")

    try:
        code = run_post.main(["--topic", "Saturday sourdough class", "--dry-run"], llm=MockLLM(script()),
                             input_fn=never_asked, env_file=None)
        run_file = sorted((work_dir / "runs").glob("run_*.json"))[-1]
        return code, trace.read_run(run_file.stem)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="autopilot_demo_") as tmp:
        code, events = run_demo(Path(tmp))
    print("\n--- trace lines that matter ---")
    for e in events:
        if e.kind in ("decision", "guardrail") or e.agent == "critic":
            out = e.summary_out.replace("\n", " ")
            print(f"{e.ts:%H:%M:%S} {e.agent:<8} {e.kind:<9} ok={str(e.ok):<5} {out[:150]}")
    print(f"\nexit code {code} (5 = blocked by a guardrail); nothing was published or written to data/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
