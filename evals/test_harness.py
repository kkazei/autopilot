"""Harness core tests (D1-B): schemas, trace and guardrails. No network, temp data dirs only."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness import guardrails, trace
from harness.schemas import (
    BrandBrief,
    Critique,
    Draft,
    Learning,
    PlannedPost,
    TraceEvent,
    WeekPlan,
    apply_threshold,
    passes_threshold,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
BRIEF = {"banned_phrases": ["act now", "Limited Time Only", "gluten-free", "cure"]}
REASONS = {"voice": "Warm.", "clarity": "One idea.", "cta": "Clear ask.", "policy_risk": "No claims."}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv(trace.DATA_DIR_ENV, str(tmp_path))
    return tmp_path


@pytest.fixture
def run_id() -> str:
    return trace.start_run()


def critique(voice=5, clarity=5, cta=5, policy_risk=5, passed=False) -> Critique:
    return Critique(voice=voice, clarity=clarity, cta=cta, policy_risk=policy_risk, reasons=REASONS, passed=passed)


def planned(i: int) -> dict:
    return {"id": f"p{i}", "day": "2026-10-23", "topic": "crust", "angle": "sound", "goal": "engagement"}


def published(*minutes_ago: int) -> list[dict]:
    return [{"posted_at": (NOW - timedelta(minutes=m)).isoformat()} for m in minutes_ago]


# ---------- schemas ----------

def test_planned_post_rejects_unknown_goal():
    with pytest.raises(ValidationError):
        PlannedPost.model_validate({**planned(1), "goal": "virality"})


@pytest.mark.parametrize("count, valid", [(2, False), (3, True), (7, True), (8, False)])
def test_week_plan_requires_3_to_7_posts(count, valid):
    data = {"week_of": "2026-10-26", "posts": [planned(i) for i in range(count)], "rationale": "r"}
    if valid:
        assert len(WeekPlan.model_validate(data).posts) == count
    else:
        with pytest.raises(ValidationError):
            WeekPlan.model_validate(data)


def test_draft_accepts_exactly_300_chars_and_rejects_301():
    assert Draft(post_id="p1", text="x" * 300, attempt=1)
    with pytest.raises(ValidationError):
        Draft(post_id="p1", text="x" * 301, attempt=1)


@pytest.mark.parametrize("attempt", [0, 4])
def test_draft_attempt_must_be_1_to_3(attempt):
    with pytest.raises(ValidationError):
        Draft(post_id="p1", text="hi", attempt=attempt)


@pytest.mark.parametrize("score", [0, 6])
def test_critique_scores_must_be_1_to_5(score):
    with pytest.raises(ValidationError):
        critique(voice=score)


def test_critique_requires_a_reason_per_score():
    with pytest.raises(ValidationError, match="policy_risk"):
        Critique(voice=5, clarity=5, cta=5, policy_risk=5, reasons={**REASONS, "policy_risk": " "})


def test_trace_event_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        TraceEvent(ts=NOW, run_id="r", agent="harness", kind="publish", summary_in="", summary_out="", ok=True)


def test_learning_metrics_must_be_ints():
    with pytest.raises(ValidationError):
        Learning(run_id="r", post_id="p", metrics={"likes": "many"}, insight="i")


def test_repo_brand_brief_is_valid():
    brief = BrandBrief.model_validate_json((REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))
    assert len(brief.voice) == 3 and brief.banned_phrases


@pytest.mark.parametrize("scores, expected", [
    ((4, 4, 4, 4), True),
    ((5, 5, 5, 3), False),
    ((3, 5, 5, 5), False),
])
def test_passes_threshold_requires_every_score_at_least_min(scores, expected):
    assert passes_threshold(critique(*scores)) is expected


def test_passes_threshold_custom_min_score():
    assert passes_threshold(critique(3, 3, 3, 3), min_score=3)


def test_model_claimed_passed_is_overwritten_by_harness():
    """A model that says passed=true with a failing score must not pass (rule 5)."""
    claimed = Critique.model_validate({"voice": 2, "clarity": 5, "cta": 5, "policy_risk": 5,
                                       "reasons": REASONS, "passed": True})
    assert apply_threshold(claimed).passed is False
    assert apply_threshold(critique(passed=False)).passed is True


# ---------- trace ----------

def test_start_run_creates_empty_trace(run_id, data_dir):
    path = data_dir / "runs" / f"{run_id}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == []


def test_log_event_appends_in_order(run_id):
    trace.log_event(run_id, "writer", "llm_call", "in1", "out1", ok=True, model="m", latency_ms=5)
    trace.log_event(run_id, "harness", "decision", "in2", "out2", ok=False)
    events = trace.read_run(run_id)
    assert [e.summary_in for e in events] == ["in1", "in2"]
    assert events[0].model == "m" and events[0].latency_ms == 5 and events[1].ok is False


def test_log_event_creates_directories_for_new_run(data_dir):
    trace.log_event("fresh_run", "harness", "decision", "a", "b", ok=True)
    assert (data_dir / "runs" / "fresh_run.json").exists()


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "x" * 81])
def test_run_id_cannot_escape_runs_dir(bad):
    with pytest.raises(ValueError):
        trace.run_path(bad)


def test_trace_redacts_secrets(run_id, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "canary-key-value-123")
    trace.log_event(run_id, "harness", "llm_call",
                    "key canary-key-value-123 and sk-or-v1-abcdef and Authorization: Bearer tok.en",
                    '{"user_id": "user_42", "pw": "abcd-efgh-ijkl-mnop"}', ok=True)
    raw = trace.run_path(run_id).read_text(encoding="utf-8")
    for secret in ("canary-key-value-123", "sk-or-v1-abcdef", "tok.en", "user_42", "abcd-efgh-ijkl-mnop"):
        assert secret not in raw


def test_trace_truncates_long_summaries_unless_told_not_to(run_id):
    trace.log_event(run_id, "harness", "decision", "x" * 5000, "y", ok=True)
    trace.log_event(run_id, "harness", "decision", "x" * 5000, "y", ok=True, truncate=False)
    short, full = trace.read_run(run_id)
    assert len(short.summary_in) < 2100 and "truncated" in short.summary_in
    assert len(full.summary_in) == 5000


def test_corrupt_trace_fails_closed_and_is_not_overwritten(run_id):
    path = trace.run_path(run_id)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(trace.TraceWriteError):
        trace.log_event(run_id, "harness", "decision", "a", "b", ok=True)
    assert path.read_text(encoding="utf-8") == "{not json"


def test_concurrent_writers_lose_no_events(run_id):
    def write(n: int) -> None:
        for i in range(10):
            trace.log_event(run_id, "harness", "decision", f"{n}-{i}", "", ok=True)

    threads = [threading.Thread(target=write, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(trace.read_run(run_id)) == 50


def test_step_logs_ok_with_latency(run_id):
    with trace.step(run_id, "critic", "llm_call", "score draft") as s:
        s.summary_out, s.model = "scored", "m1"
    [event] = trace.read_run(run_id)
    assert event.ok and event.summary_out == "scored" and event.model == "m1" and event.latency_ms is not None


def test_step_logs_failure_and_reraises(run_id):
    with pytest.raises(RuntimeError):
        with trace.step(run_id, "writer", "llm_call", "draft"):
            raise RuntimeError("model down")
    [event] = trace.read_run(run_id)
    assert not event.ok and "model down" in event.summary_out


# ---------- guardrails ----------

def test_check_length_boundary():
    assert guardrails.check_length("x" * 300)["ok"]
    result = guardrails.check_length("x" * 301)
    assert not result["ok"] and "301" in result["reasons"][0]


def test_check_length_rejects_empty():
    assert not guardrails.check_length("   ")["ok"]


@pytest.mark.parametrize("text", [
    "ACT NOW and book a class",
    "this is a limited time only offer",
    "Our GLUTEN FREE loaf",
    "Act​ now",               # zero-width space
    "ＡＣＴ ＮＯＷ",              # full-width letters
    "a.c.t now? no: act, now!",
])
def test_check_banned_catches_mixed_case_and_obfuscation(text):
    result = guardrails.check_banned(text, BRIEF)
    assert not result["ok"] and result["reasons"][0].startswith("contains banned phrase")


def test_check_banned_matches_whole_words_only():
    assert guardrails.check_banned("Our crust is secure and crackly.", BRIEF)["ok"]


def test_check_banned_fails_closed_without_a_list():
    assert not guardrails.check_banned("fine text", {})["ok"]
    assert not guardrails.check_banned("fine text", {"banned_phrases": "act now"})["ok"]


def test_rate_cap_allows_third_post_and_blocks_fourth():
    assert guardrails.check_rate_cap(NOW, published(120, 240))["ok"]
    result = guardrails.check_rate_cap(NOW, published(120, 240, 360))
    assert not result["ok"] and "3 posts in the last 24 hours" in result["reasons"][0]


def test_rate_cap_window_boundary_is_24_hours():
    assert guardrails.check_rate_cap(NOW, published(120, 240, 24 * 60))["ok"]
    assert not guardrails.check_rate_cap(NOW, published(120, 240, 24 * 60 - 1))["ok"]


def test_rate_cap_gap_boundary_is_60_minutes():
    assert guardrails.check_rate_cap(NOW, published(60))["ok"]
    result = guardrails.check_rate_cap(NOW, published(59))
    assert not result["ok"] and "59 minutes ago" in result["reasons"][0]


def test_rate_cap_fails_closed_on_unreadable_log():
    assert not guardrails.check_rate_cap(NOW, [{"posted_at": "yesterday"}])["ok"]
    assert not guardrails.check_rate_cap(NOW, [{"posted_at": "2026-10-22T10:00:00"}])["ok"]  # naive
    assert not guardrails.check_rate_cap(NOW, [{}])["ok"]


def test_rate_cap_requires_aware_now():
    with pytest.raises(ValueError):
        guardrails.check_rate_cap(NOW.replace(tzinfo=None), [])


def test_check_duplicate_flags_near_duplicates():
    original = "Fresh sourdough out of the oven at 7am. Come smell it!"
    assert not guardrails.check_duplicate("fresh sourdough out of the oven at 7 am - come smell it", [original])["ok"]
    assert guardrails.check_duplicate("Saturday class: learn to shape a boule.", [original])["ok"]


def test_check_duplicate_threshold_is_configurable():
    a, b = "learn to shape a boule this saturday", "learn to shape a batard this saturday"
    assert guardrails.check_duplicate(a, [b], threshold=0.95)["ok"]
    assert not guardrails.check_duplicate(a, [b], threshold=0.7)["ok"]


@pytest.mark.parametrize("answer, ok", [("y", True), ("YES", True), ("", False), ("n", False), ("sure", False)])
def test_require_approval_needs_explicit_yes(answer, ok):
    assert guardrails.require_approval("post", True, input_fn=lambda _: answer)["ok"] is ok


def test_require_approval_closed_stdin_means_no():
    def eof(_: str) -> str:
        raise EOFError

    assert not guardrails.require_approval("post", True, input_fn=eof)["ok"]


def test_require_approval_disabled_never_prompts():
    def boom(_: str) -> str:
        raise AssertionError("prompted")

    assert guardrails.require_approval("post", False, input_fn=boom)["ok"]


def run_all(run_id: str, text: str, **overrides) -> dict:
    kwargs = dict(run_id=run_id, now=NOW, published_log=[], recent_texts=[], approval_enabled=False)
    return guardrails.run_all(text, BRIEF, **{**kwargs, **overrides})


def test_run_all_passes_and_logs_every_check(run_id):
    result = run_all(run_id, "Warm bread, Saturday class. Book a seat.")
    assert result["ok"] and result["reasons"] == []
    events = trace.read_run(run_id)
    assert [e.summary_in.split(" | ")[0] for e in events] == [
        "check_length", "check_banned", "check_rate_cap", "check_duplicate", "require_approval"]
    assert all(e.kind == "guardrail" and e.agent == "harness" and e.ok for e in events)


def test_run_all_reports_every_failure_and_skips_approval(run_id):
    def boom(_: str) -> str:
        raise AssertionError("reviewer was asked about a blocked draft")

    result = run_all(run_id, "Act now!", published_log=published(10), approval_enabled=True, input_fn=boom)
    assert not result["ok"]
    assert any(r.startswith("check_banned") for r in result["reasons"])
    assert any(r.startswith("check_rate_cap") for r in result["reasons"])
    failed = {e.summary_in.split(" | ")[0] for e in trace.read_run(run_id) if not e.ok}
    assert failed == {"check_banned", "check_rate_cap", "require_approval"}


def test_run_all_blocks_when_reviewer_declines(run_id):
    result = run_all(run_id, "Warm bread.", approval_enabled=True, input_fn=lambda _: "n")
    assert not result["ok"] and result["reasons"] == ["require_approval: human reviewer did not approve"]
