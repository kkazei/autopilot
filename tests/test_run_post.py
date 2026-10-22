"""scripts/run_post.py tests (D1-D): approval on by default, guardrails before publish, rate cap before any model call.

MockLLM and temp data dirs only; Bluesky is replaced by a fake that records calls.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from harness import trace
from harness.fileio import read_jsonl
from harness.llm import LLMUnavailable, MockLLM
from harness.publish import PublishRefused, _harness_env, approved_path, publish
from harness.schemas import Critique, Draft
from mcp_server import bluesky, server
from scripts import run_post

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
GOOD = json.dumps({"text": "Saturday's class starts with flour on your hands. Save a seat at the link."})
REASONS = {d: f"{d} is fine." for d in ("voice", "clarity", "cta", "policy_risk")}


def scores(n: int = 5) -> str:
    return json.dumps({"voice": n, "clarity": n, "cta": n, "policy_risk": n, "reasons": REASONS})


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch) -> Path:
    shutil.copy(REPO_ROOT / "data" / "brand_brief.json", tmp_path / "brand_brief.json")
    monkeypatch.setenv(trace.DATA_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(server.CALL_LOG_ENV, str(tmp_path / "calls.jsonl"))
    for var in (server.ROLE_ENV, server.TOKEN_ENV, server.DRY_RUN_ENV):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def bsky(monkeypatch) -> list[str]:
    """Fake live client: records texts instead of posting."""
    sent: list[str] = []

    def fake_post(text):
        sent.append(text)
        return {"uri": "at://did:plc:test/app.bsky.feed.post/1", "cid": "c1"}

    monkeypatch.setattr(bluesky, "post", fake_post)
    return sent


def run(argv, script, answers=("y",)):
    """Run the CLI with a MockLLM; `answers` feeds the approval prompt (EOFError when exhausted, like closed stdin)."""
    prompts: list[str] = []
    queue = list(answers)

    def input_fn(prompt: str) -> str:
        prompts.append(prompt)
        if not queue:
            raise EOFError
        return queue.pop(0)

    llm = MockLLM(list(script))
    code = run_post.main(["--topic", "Saturday class", *argv], llm=llm, input_fn=input_fn, now=NOW, env_file=None)
    return code, llm, prompts


def approved() -> list[dict]:
    return read_jsonl(approved_path())[0]


def published_calls(data: Path) -> list[dict]:
    records, _ = read_jsonl(data / "calls.jsonl")
    return [r for r in records if r["tool"] == "publish_post"]


def write_approved(*rows: dict) -> None:
    approved_path().parent.mkdir(parents=True, exist_ok=True)
    approved_path().write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


# ---------- approval ----------

def test_approval_is_on_by_default():
    assert run_post.parse_args(["--topic", "x"]).approve is True


def test_dry_run_asks_for_approval_and_publishes_a_dryrun_uri(env, bsky):
    code, _, prompts = run(["--dry-run"], [GOOD, scores()])
    assert code == run_post.EXIT_PUBLISHED and len(prompts) == 1 and "flour" in prompts[0]
    [row] = approved()
    assert row["dry_run"] is True and row["uri"].startswith("dryrun://") and row["scores"]["cta"] == 5
    assert bsky == []


def test_live_publish_needs_yes_and_goes_through_the_harness(env, bsky):
    code, _, _ = run([], [GOOD, scores()], answers=("yes",))
    assert code == run_post.EXIT_PUBLISHED and len(bsky) == 1
    [row] = approved()
    assert row["dry_run"] is False and row["uri"].startswith("at://")
    assert [r.get("phase") for r in published_calls(env)] == ["pending", None]
    assert os.environ.get(server.ROLE_ENV) is None and os.environ.get(server.TOKEN_ENV) is None


@pytest.mark.parametrize("answers", [(), ("n",), ("",), ("sure",)])
def test_anything_but_yes_blocks_publish(env, bsky, answers):
    code, _, prompts = run([], [GOOD, scores()], answers=answers)
    assert code == run_post.EXIT_BLOCKED and len(prompts) == 1
    assert bsky == [] and approved() == [] and published_calls(env) == []


def test_no_approve_is_refused_for_a_live_run(env, bsky):
    code, llm, _ = run(["--no-approve"], [GOOD, scores()])
    assert code == run_post.EXIT_REFUSED and llm.calls == [] and bsky == []
    assert not (env / "runs").exists()


def test_no_approve_with_dry_run_skips_the_prompt(env, bsky):
    code, _, prompts = run(["--dry-run", "--no-approve"], [GOOD, scores()])
    assert code == run_post.EXIT_PUBLISHED and prompts == [] and approved()[0]["dry_run"] is True


# ---------- the fourth required case: no publish on a guardrail failure ----------

def test_guardrail_failure_means_no_publish(env, bsky, monkeypatch):
    monkeypatch.setattr(run_post, "publish", lambda *a, **k: pytest.fail("publish called after a guardrail failure"))
    banned = json.dumps({"text": "Act now: our class is the best bakery in town experience."})
    code, _, prompts = run([], [banned, scores()])  # the mock critic waves it through; the guardrail must not
    assert code == run_post.EXIT_BLOCKED and prompts == []  # the reviewer is never asked about a blocked draft
    assert bsky == [] and approved() == [] and published_calls(env) == []
    blocked = [e for e in trace.read_run(sorted((env / "runs").glob("*.json"))[0].stem)
               if e.kind == "guardrail" and not e.ok]
    assert any("check_banned" in e.summary_in for e in blocked)


# ---------- rate cap, escalation, failures ----------

def test_rate_cap_is_checked_before_any_model_call(env, bsky):
    write_approved({"text": "earlier", "posted_at": (NOW - timedelta(minutes=10)).isoformat(), "dry_run": False})
    code, llm, _ = run([], [GOOD, scores()])
    assert code == run_post.EXIT_BLOCKED and llm.calls == []


def test_dry_run_rows_do_not_count_toward_the_rate_cap(env, bsky):
    write_approved({"text": "rehearsal", "posted_at": (NOW - timedelta(minutes=10)).isoformat(), "dry_run": True})
    code, _, _ = run(["--dry-run"], [GOOD, scores()])
    assert code == run_post.EXIT_PUBLISHED


def test_escalated_post_is_not_published(env, bsky):
    code, _, prompts = run([], [GOOD, scores(2)] * 3)
    assert code == run_post.EXIT_ESCALATED and prompts == [] and bsky == [] and approved() == []


def test_llm_failure_exits_cleanly_without_publishing(env, bsky):
    code, _, _ = run([], [LLMUnavailable("all models down")])
    assert code == run_post.EXIT_FAILED and bsky == [] and approved() == []


# ---------- harness.publish preconditions ----------

def critique(n: int) -> Critique:
    return Critique(voice=n, clarity=n, cta=n, policy_risk=n, reasons=REASONS)


DRAFT = Draft(post_id="post_x", text="Warm rye.", attempt=1)


@pytest.mark.parametrize("crit, gate", [(critique(3), {"ok": True}), (critique(5), {"ok": False, "reasons": ["x"]}),
                                        (critique(5), {})])
def test_publish_refuses_unless_critique_and_guardrails_pass(env, bsky, crit, gate):
    run_id = trace.start_run()
    with pytest.raises(PublishRefused):
        publish(run_id, DRAFT, crit, gate, dry_run=False)
    assert bsky == [] and published_calls(env) == []


def test_harness_env_is_restored_after_the_call(monkeypatch):
    monkeypatch.setenv(server.DRY_RUN_ENV, "0")
    with _harness_env(dry_run=True):
        assert os.environ[server.ROLE_ENV] == "harness" and len(os.environ[server.TOKEN_ENV]) >= 32
        assert os.environ[server.DRY_RUN_ENV] == "1"
    assert server.ROLE_ENV not in os.environ and server.TOKEN_ENV not in os.environ
    assert os.environ[server.DRY_RUN_ENV] == "0"


def test_publish_token_never_reaches_the_trace_or_logs(env, bsky, monkeypatch):
    import harness.publish as publish_mod

    token = "publishtoken" + "q" * 20
    real = publish_mod.secrets.token_hex
    monkeypatch.setattr(publish_mod.secrets, "token_hex", lambda n=None: token if n == 16 else real(n))
    code, _, _ = run(["--dry-run"], [GOOD, scores()])
    assert code == run_post.EXIT_PUBLISHED
    run_file = sorted((env / "runs").glob("*.json"))[0].read_text(encoding="utf-8")
    calls = (env / "calls.jsonl").read_text(encoding="utf-8")
    assert token not in run_file and token not in calls and token not in approved_path().read_text(encoding="utf-8")
