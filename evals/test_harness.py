"""Harness core tests (D1-B, D1-C): schemas, trace, guardrails and the LLM chain. No network, temp data dirs only."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness import guardrails, llm, trace
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


def test_truncation_keeps_the_head_and_the_tail_and_says_how_much_was_cut(run_id):
    text = "START-" + "m" * 5000 + "-THE-DRAFT-IS-HERE"
    trace.log_event(run_id, "critic", "llm_call", text, "ok", ok=True)
    [event] = trace.read_run(run_id)
    assert event.summary_in.startswith("START-") and event.summary_in.endswith("-THE-DRAFT-IS-HERE")
    assert f"[truncated {len(text) - trace.SUMMARY_MAX_CHARS} chars]" in event.summary_in
    assert len(event.summary_in) < trace.SUMMARY_MAX_CHARS + 100
    assert len(event.summary_in.split("...[truncated")[1].split("]...")[1]) == trace.SUMMARY_MAX_CHARS * 3 // 4


def test_a_secret_on_the_cut_is_redacted_whole_not_left_half_visible(run_id, monkeypatch):
    secret = "canary-secret-value-987654"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    cut = trace.SUMMARY_MAX_CHARS // 4
    text = "a" * (cut - 10) + secret + "b" * 4000  # the secret starts 10 characters before the head ends
    trace.log_event(run_id, "harness", "decision", text, "ok", ok=True)
    [event] = trace.read_run(run_id)
    assert secret not in event.summary_in and "canary-sec" not in event.summary_in
    assert "[REDACTED:" in event.summary_in  # the cut may take the end of the marker, never a piece of the secret


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


# ---------- LLM fallback chain ----------

KEY = "sk-or-v1-" + "0" * 40
CHAIN = ["a/one:free", "b/two:free", "c/three:free"]
GOOD = json.dumps({"model": "a/one:free", "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 12, "completion_tokens": 3}})
MSGS = [{"role": "user", "content": "hi"}]


class ScriptedTransport:
    """Plays back one outcome per request: a (status, body) pair or an exception to raise."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests: list[dict] = []

    def __call__(self, url, headers, body, timeout_s):
        self.requests.append({"headers": dict(headers), "payload": json.loads(body)})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return llm.HttpResponse(*outcome)

    @property
    def models(self) -> list[str]:
        return [r["payload"]["model"] for r in self.requests]


def chain(*outcomes, models=CHAIN, max_tries=3) -> tuple[llm.OpenRouterLLM, ScriptedTransport, list[float]]:
    transport, sleeps = ScriptedTransport(*outcomes), []
    client = llm.OpenRouterLLM(models, KEY, transport=transport, sleep=sleeps.append, jitter=lambda: 0.5,
                               max_tries=max_tries)
    return client, transport, sleeps


def test_temperature_is_not_sent_unless_the_client_sets_it(run_id):
    client, transport, _ = chain((200, GOOD))
    client.chat(run_id, "critic", MSGS)
    assert "temperature" not in transport.requests[0]["payload"]


def test_a_client_temperature_of_zero_is_sent_on_every_attempt_including_fallbacks(run_id):
    transport = ScriptedTransport((429, "busy"), (200, GOOD))
    client = llm.OpenRouterLLM(CHAIN, KEY, transport=transport, sleep=lambda s: None, jitter=lambda: 0.5,
                               temperature=0.0)
    client.chat(run_id, "critic", MSGS)
    assert len(transport.requests) == 2
    assert all(r["payload"]["temperature"] == 0.0 for r in transport.requests)  # 0 is sent, not treated as "unset"


def test_models_from_env_parses_and_refuses_paid_ids():
    assert llm.models_from_env({llm.MODELS_ENV: " a/one:free, b/two:free ,"}) == ["a/one:free", "b/two:free"]
    with pytest.raises(llm.LLMConfigError, match="non-free"):
        llm.models_from_env({llm.MODELS_ENV: "a/one:free,openai/gpt-5"})
    with pytest.raises(llm.LLMConfigError, match="empty"):
        llm.models_from_env({})


def test_missing_key_is_refused_before_any_request(monkeypatch):
    monkeypatch.delenv(llm.KEY_ENV, raising=False)
    with pytest.raises(llm.LLMConfigError):
        llm.OpenRouterLLM(CHAIN, transport=lambda *a: pytest.fail("request sent"))


def test_first_model_success_records_model_latency_and_tokens(run_id):
    client, transport, _ = chain((200, GOOD))
    response = client.chat(run_id, "writer", MSGS)
    assert response.content == "hello" and response.prompt_tokens == 12 and response.completion_tokens == 3
    assert transport.models == ["a/one:free"] and transport.requests[0]["payload"]["stream"] is False
    [event] = trace.read_run(run_id)
    assert event.kind == "llm_call" and event.ok and event.model == "a/one:free" and event.latency_ms is not None
    assert "tokens in=12 out=3" in event.summary_out


def test_429_backs_off_then_retries_same_model(run_id):
    client, transport, sleeps = chain((429, "busy"), (200, GOOD))
    assert client.chat(run_id, "writer", MSGS).content == "hello"
    assert transport.models == ["a/one:free", "a/one:free"] and sleeps == [2.0]
    kinds = [(e.kind, e.ok) for e in trace.read_run(run_id)]
    assert kinds == [("llm_call", False), ("decision", True), ("llm_call", True)]


def test_backoff_is_exponential_jittered_and_capped():
    client, _, _ = chain()
    assert [client.backoff_s(n) for n in (1, 2, 3)] == [2.0, 4.0, 8.0]
    client._jitter = lambda: 1.0
    assert client.backoff_s(10) == llm.BACKOFF_CAP_S * 1.5


def test_three_transient_failures_fall_back_to_next_model(run_id):
    client, transport, sleeps = chain((429, ""), (503, ""), TimeoutError("slow"), (200, GOOD))
    assert client.chat(run_id, "planner", MSGS).content == "hello"
    assert transport.models == ["a/one:free"] * 3 + ["b/two:free"] and len(sleeps) == 2
    decisions = [e.summary_out for e in trace.read_run(run_id) if e.kind == "decision"]
    assert decisions[-1] == "fallback to b/two:free"


def test_404_skips_to_next_model_without_retry(run_id):
    client, transport, sleeps = chain((404, "no endpoint"), (200, GOOD))
    client.chat(run_id, "writer", MSGS)
    assert transport.models == ["a/one:free", "b/two:free"] and sleeps == []


def test_404_model_is_not_asked_again_on_later_calls_of_the_same_client(run_id):
    client, transport, _ = chain((404, "retired"), (200, GOOD), (200, GOOD), (200, GOOD))
    for _ in range(3):
        client.chat(run_id, "writer", MSGS)
    assert transport.models == ["a/one:free", "b/two:free", "b/two:free", "b/two:free"]
    marks = [e for e in trace.read_run(run_id) if e.summary_out.startswith("dead for the rest of this run")]
    assert len(marks) == 1 and marks[0].model == "a/one:free" and marks[0].ok is False


def test_dead_model_is_skipped_in_the_fallback_message_and_costs_no_budget_later(run_id):
    client, transport, _ = chain((404, "retired"), (200, GOOD), (200, GOOD))
    budget = llm.Budget(limit=2)
    client.chat(run_id, "writer", MSGS, budget=budget)  # 404 + success = 2 attempts
    assert budget.used == 2
    fresh = llm.Budget(limit=1)
    client.chat(run_id, "writer", MSGS, budget=fresh)  # only the live model is asked, so 1 attempt is enough
    assert fresh.used == 1 and transport.models[-1] == "b/two:free"


def test_every_model_dead_raises_unavailable_without_further_requests(run_id):
    client, transport, _ = chain(*[(404, "gone")] * len(CHAIN))
    with pytest.raises(llm.LLMUnavailable):
        client.chat(run_id, "writer", MSGS)
    with pytest.raises(llm.LLMUnavailable):
        client.chat(run_id, "writer", MSGS)
    assert transport.models == CHAIN


def test_400_and_truncation_do_not_mark_a_model_dead(run_id):
    truncated = json.dumps({"choices": [{"message": {"content": "{"}, "finish_reason": "length"}]})
    client, transport, _ = chain((400, "rejects this request"), (200, GOOD), (200, truncated), (200, GOOD))
    client.chat(run_id, "writer", MSGS)
    client.chat(run_id, "writer", MSGS)
    assert transport.models[2] == "a/one:free"  # asked again on the second call
    assert client._dead == set()


@pytest.mark.parametrize("status", [401, 402, 403])
def test_auth_errors_stop_without_fallback(run_id, status):
    client, transport, _ = chain((status, "nope"))
    with pytest.raises(llm.LLMAuthError):
        client.chat(run_id, "writer", MSGS)
    assert transport.models == ["a/one:free"]
    assert trace.read_run(run_id)[-1].summary_out == "stop: auth or billing error, no fallback"


def test_error_inside_a_200_body_is_classified_by_its_code(run_id):
    embedded = json.dumps({"error": {"code": 404, "message": "Provider returned error"}})
    client, transport, sleeps = chain((200, embedded), (200, GOOD))
    client.chat(run_id, "writer", MSGS)
    assert transport.models == ["a/one:free", "b/two:free"] and sleeps == []


def test_empty_answer_is_treated_as_transient(run_id):
    empty = json.dumps({"choices": [{"message": {"content": ""}}]})
    client, transport, _ = chain((200, empty), (200, GOOD))
    assert client.chat(run_id, "writer", MSGS).content == "hello"
    assert transport.models == ["a/one:free", "a/one:free"]


def test_every_model_failing_raises_after_a_bounded_number_of_requests(run_id):
    client, transport, _ = chain(*[(500, "")] * 6, max_tries=2)
    with pytest.raises(llm.LLMUnavailable):
        client.chat(run_id, "writer", MSGS)
    assert len(transport.requests) == 6
    assert trace.read_run(run_id)[-1].summary_out == "no models left"


def test_tool_calls_are_returned_and_tools_sent(run_id):
    body = json.dumps({"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "get_brand_brief", "arguments": "{}"}}]},
        "finish_reason": "tool_calls"}]})
    tool = {"type": "function", "function": {"name": "get_brand_brief", "parameters": {"type": "object"}}}
    client, transport, _ = chain((200, body))
    response = client.chat(run_id, "writer", MSGS, tools=[tool])
    assert response.tool_calls[0]["function"]["name"] == "get_brand_brief"
    assert transport.requests[0]["payload"]["tools"] == [tool]


def test_key_is_sent_in_header_but_never_traced(run_id, monkeypatch):
    monkeypatch.setenv(llm.KEY_ENV, KEY)
    client, transport, _ = chain((401, f"bad key {KEY}"))
    with pytest.raises(llm.LLMAuthError):
        client.chat(run_id, "writer", MSGS)
    assert transport.requests[0]["headers"]["Authorization"] == f"Bearer {KEY}"
    assert KEY not in trace.run_path(run_id).read_text(encoding="utf-8")
    assert KEY not in repr(client)


@pytest.mark.parametrize("text", [
    '{"post_id": "p1", "text": "Rye.", "attempt": 1}',
    '```json\n{"post_id": "p1", "text": "Rye.", "attempt": 1}\n```',
    'Here you go: {"post_id": "p1", "text": "Rye.", "attempt": 1} Enjoy!',
])
def test_chat_json_accepts_fenced_or_wrapped_json(run_id, text):
    assert llm.MockLLM([text]).chat_json(run_id, "writer", MSGS, Draft).text == "Rye."


def test_chat_json_repairs_once_and_shows_the_model_its_errors(run_id):
    mock = llm.MockLLM(['{"post_id": "p1", "attempt": 1}', '{"post_id": "p1", "text": "Rye.", "attempt": 1}'])
    assert mock.chat_json(run_id, "writer", MSGS, Draft).text == "Rye."
    repair_prompt = mock.calls[1][-1]["content"]
    assert "text" in repair_prompt and "Field required" in repair_prompt
    outs = [e.summary_out for e in trace.read_run(run_id) if e.kind == "decision"]
    assert outs[0].startswith("repair attempt") and outs[1] == "repair succeeded"


def test_chat_json_fails_cleanly_after_one_repair(run_id):
    mock = llm.MockLLM(["not json", "still not json", "never asked"])
    with pytest.raises(llm.LLMOutputError):
        mock.chat_json(run_id, "critic", MSGS, Critique)
    assert len(mock.calls) == 2
    last = trace.read_run(run_id)[-1]
    assert last.kind == "decision" and not last.ok and last.summary_out.startswith("repair failed")


def test_mock_llm_logs_like_the_real_chain_and_raises_when_exhausted(run_id):
    mock = llm.MockLLM(["ok"])
    mock.chat(run_id, "analyst", MSGS)
    with pytest.raises(llm.LLMUnavailable):
        mock.chat(run_id, "analyst", MSGS)
    [event] = trace.read_run(run_id)
    assert event.kind == "llm_call" and event.model == "mock/model:free"


def test_budget_stops_the_chain_before_its_own_retry_limit(run_id):
    client, transport, _ = chain(*[(429, "")] * 9)
    with pytest.raises(llm.LLMBudgetExceeded):
        client.chat(run_id, "critic", MSGS, budget=llm.Budget(4))
    assert len(transport.requests) == 4
    assert trace.read_run(run_id)[-1].summary_out == "stop: upstream attempt budget of 4 used up"


def test_budget_is_shared_by_tool_rounds_and_repair(run_id):
    mock = llm.MockLLM([TOOL_CALL, "not json", "never asked"])
    with pytest.raises(llm.LLMBudgetExceeded):
        mock.chat_json(run_id, "writer", MSGS, Draft, tools=[BRIEF_TOOL], run_tool=lambda n, a: "{}",
                       budget=llm.Budget(2))
    assert len(mock.calls) == 2


def test_role_budgets_match_decision_4_4():
    assert llm.ROLE_BUDGETS == {"planner": 12, "writer": 8, "critic": 4, "analyst": 12}


TOOL_CALL = llm.LLMResponse(model="m", content=None, tool_calls=[
    {"id": "c1", "type": "function", "function": {"name": "get_brand_brief", "arguments": "{}"}}])
BRIEF_TOOL = {"type": "function", "function": {"name": "get_brand_brief", "parameters": {"type": "object"}}}


def test_chat_json_runs_tools_then_validates(run_id):
    ran: list[tuple[str, dict]] = []
    mock = llm.MockLLM([TOOL_CALL, '{"post_id": "p1", "text": "Rye.", "attempt": 1}'])
    out = mock.chat_json(run_id, "writer", MSGS, Draft, tools=[BRIEF_TOOL],
                         run_tool=lambda n, a: ran.append((n, a)) or '{"name": "B"}')
    assert out.text == "Rye." and ran == [("get_brand_brief", {})]
    assert mock.calls[1][-2]["tool_calls"] and mock.calls[1][-1] == {
        "role": "tool", "tool_call_id": "c1", "content": '{"name": "B"}'}


def test_tool_rounds_are_capped_and_repair_goes_out_without_tools(run_id):
    mock = llm.MockLLM([TOOL_CALL] * 3 + ['{"post_id": "p1", "text": "Rye.", "attempt": 1}'])
    out = mock.chat_json(run_id, "writer", MSGS, Draft, tools=[BRIEF_TOOL], run_tool=lambda n, a: "{}")
    assert out.text == "Rye." and len(mock.calls) == 1 + llm.MAX_TOOL_ROUNDS + 1
    assert mock.tools_offered[-1] == []


def test_overrides_replace_model_supplied_fields(run_id):
    mock = llm.MockLLM(['{"post_id": "fake", "text": "Rye.", "attempt": 3}'])
    out = mock.chat_json(run_id, "writer", MSGS, Draft, overrides={"post_id": "p9", "attempt": 1})
    assert (out.post_id, out.attempt) == ("p9", 1)


CUT_OFF = json.dumps({"model": "a/one:free", "choices": [{"message": {"content": '{"text":"In Saturday\'s class, Small'},
                                                         "finish_reason": "length"}],
                      "usage": {"prompt_tokens": 1166, "completion_tokens": 1024}})


def test_cut_off_reply_moves_to_next_model_and_is_never_validated(run_id):
    """Regression for run_20261022_092011_d8f068: a reasoning model hit max_tokens mid-JSON."""
    client, transport, sleeps = chain((200, CUT_OFF), (200, GOOD))
    response = client.chat(run_id, "writer", MSGS)
    assert response.content == "hello" and transport.models == ["a/one:free", "b/two:free"] and sleeps == []
    failed = [e for e in trace.read_run(run_id) if e.kind == "llm_call" and not e.ok]
    assert len(failed) == 1 and "truncated at max_tokens" in failed[0].summary_out


def test_cut_off_repair_falls_back_instead_of_failing_the_draft(run_id):
    bad = json.dumps({"choices": [{"message": {"content": '{"post_id": "p1", "attempt": 1}'}, "finish_reason": "stop"}]})
    fixed = json.dumps({"choices": [{"message": {"content": '{"post_id": "p1", "text": "Rye.", "attempt": 1}'},
                                     "finish_reason": "stop"}]})
    client, transport, _ = chain((200, bad), (200, CUT_OFF), (200, fixed))
    assert client.chat_json(run_id, "writer", MSGS, Draft).text == "Rye."
    assert transport.models == ["a/one:free", "a/one:free", "b/two:free"]


def test_failed_attempts_record_finish_reason_and_tokens(run_id):
    empty = json.dumps({"choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 974, "completion_tokens": 0}})
    client, _, _ = chain((200, empty), (200, CUT_OFF), (200, GOOD))
    client.chat(run_id, "writer", MSGS)
    failed = [e.summary_out for e in trace.read_run(run_id) if e.kind == "llm_call" and not e.ok]
    assert "finish=stop tokens in=974 out=0" in failed[0]
    assert "finish=length tokens in=1166 out=1024" in failed[1]


def test_default_request_allows_4096_tokens(run_id):
    client, transport, _ = chain((200, GOOD))
    client.chat(run_id, "writer", MSGS)
    assert llm.DEFAULT_MAX_TOKENS == 4096 and transport.requests[0]["payload"]["max_tokens"] == 4096


def test_repair_prompt_states_actual_length_target_and_no_thinking_aloud(run_id):
    mock = llm.MockLLM([json.dumps({"post_id": "p1", "text": "x" * 348, "attempt": 1}),
                        '{"post_id": "p1", "text": "Rye.", "attempt": 1}'])
    mock.chat_json(run_id, "writer", MSGS, Draft, repair_hint="Keep the text to 280 characters or fewer.")
    prompt = mock.calls[1][-1]["content"]
    assert "text: is 348 characters; the limit is 300" in prompt
    assert "280 characters or fewer" in prompt and "Do not explain or think aloud" in prompt


@pytest.mark.parametrize("raw, expected", [("{}", {}), ("", {}), ("not json", {}), ("[1]", {}),
                                           ('{"limit": 3}', {"limit": 3}), ({"a": 1}, {"a": 1})])
def test_tool_args_never_crash_the_loop(raw, expected):
    assert llm._tool_args(raw) == expected


# ---------- review item 7 / issue 17: banned-phrase variants ----------

REAL_BRIEF = json.loads((REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("text", [
    "Sourdough cures everything",            # inflection
    "It cured my cravings",
    "Slow fermentation is curing me",
    "c u r e for boredom",                   # spaced letters
    "c.u.r.e for boredom",                   # dotted letters
    "a.c.t now, seats are going",            # dotted letters starting with "a" (not an article here)
    "Actnow while seats last",               # no-space form
    "Glutenfree loaves this week",
    "glu-ten-free loaves this week",         # split form
    "Dont miss out on Saturday",             # missing apostrophe
    "Guaranteed result for every baker",     # singular
    "Voted the best bakery in the town",     # filler article
    "A curative crumb",                      # variants list in the brief
    "Results guaranteed, every time",
    "Do not miss out on Saturday",
])
def test_check_banned_catches_variants(text):
    result = guardrails.check_banned(text, REAL_BRIEF)
    assert not result["ok"], text


@pytest.mark.parametrize("text", [
    "Our crust is secure and crackly.",
    "Procure a little patience; the dough will rise.",
    "Currant buns and a curious crowd.",
    "React now and then, but mostly wait for the dough.",
    "The best bread in town is the one you bake yourself.",
    "Click the link here if you fancy a seat.",
])
def test_check_banned_does_not_block_ordinary_words(text):
    assert guardrails.check_banned(text, REAL_BRIEF)["ok"], text


def test_file_lock_stale_s_controls_when_a_held_lock_is_broken(tmp_path):
    import os

    from harness.fileio import LockTimeout, file_lock

    target = tmp_path / "thing"
    lock = tmp_path / "thing.lock"
    lock.write_text("123")
    old = lock.stat().st_mtime - 120  # 2 minutes old: stale at the 60s default, live at 1h
    os.utime(lock, (old, old))
    with pytest.raises(LockTimeout):
        with file_lock(target, timeout_s=0, stale_s=3600):
            pass
    assert lock.exists()
    with file_lock(target, timeout_s=0):  # default 60s: the old lock is broken
        pass
