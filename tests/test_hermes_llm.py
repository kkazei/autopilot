"""harness/hermes_llm.py: Hermes behind the LLM interface, with a fake runner that talks to the real proxy.

The fake plays Hermes: it calls the proxy over HTTP like the real thing, and writes the call-log line the real
MCP server would write. Everything between those two is the production code.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date

import pytest

from agents import critic, writer
from harness import hermes_llm, trace
from harness.fileio import append_jsonl
from harness.hermes_llm import HermesWriterLLM, runtime_from_env, with_runtime
from harness.hermes_runner import TOOL_PREFIX, HermesResult, HermesRunError, HermesSpec
from harness.llm import Budget, LLMBudgetExceeded, LLMConfigError, LLMResponse, MockLLM
from harness.schemas import BrandBrief, Draft, PlannedPost
from mcp_server import server
from tests.helpers import REPO_ROOT, data, scores  # noqa: F401 - fixture

BRIEF_TOOL = f"{TOOL_PREFIX}get_brand_brief"
TOOL_CALL = {"id": "c1", "type": "function", "function": {"name": BRIEF_TOOL, "arguments": "{}"}}
GOOD = json.dumps({"text": "Saturday's class starts with flour on your hands. Save a seat at the link."})
MESSAGES = [{"role": "system", "content": "You write one post."}, {"role": "user", "content": "Write the post."}]
SPECS = [{"type": "function", "function": {"name": "get_brand_brief", "parameters": {}}}]
BRIEF = BrandBrief.model_validate_json((REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))
PLANNED = PlannedPost(id="p1", day=date(2026, 10, 24), topic="Saturday class", angle="flour", goal="click")


def ask(spec: HermesSpec, messages: list[dict]) -> dict:
    request = urllib.request.Request(
        spec.base_url + "/chat/completions", method="POST",
        data=json.dumps({"model": spec.model_label, "messages": messages,
                         "tools": [{"type": "function", "function": {"name": f"{TOOL_PREFIX}{t}"}}
                                   for t in spec.tools]}).encode(),
        headers={"Authorization": f"Bearer {spec.proxy_token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as r:
        return json.loads(r.read())


def hermes_like(*, call_tool: bool = True, log_call: bool = True, extra_events=(), exit_code: int = 0,
                seen: list | None = None):
    """A runner that behaves like a healthy Hermes unless told otherwise."""

    def runner(spec: HermesSpec) -> HermesResult:
        if seen is not None:
            seen.append(spec)
        messages = [{"role": "system", "content": spec.system_prompt}, {"role": "user", "content": spec.user_prompt}]
        events: list[dict] = [{"type": "system", "subtype": "init"}]
        reply = ask(spec, messages)
        if call_tool:
            events.append({"type": "tool_use", "name": BRIEF_TOOL, "input": {}})
            if log_call:
                append_jsonl(spec.call_log, {"role": spec.role, "tool": "get_brand_brief", "args": "{}", "ok": True,
                                             "receipt": "abc123", "result": "{...}", "latency_ms": 2})
            tool_msg = {"role": "assistant", "content": "", "tool_calls": reply["choices"][0]["message"]["tool_calls"]}
            reply = ask(spec, [*messages, tool_msg, {"role": "tool", "tool_call_id": "c1", "content": "{}"}])
        text = reply["choices"][0]["message"]["content"]
        events.extend(extra_events)
        events.append({"type": "result", "exit_code": exit_code, "text": text})
        return HermesResult(exit_code, text, "", "", tuple(events), 0.5)

    return runner


def script(*items):
    return MockLLM(list(items))


def decisions(run_id: str) -> list[str]:
    return [f"{e.summary_in} => {e.summary_out}" for e in trace.read_run(run_id) if e.kind == "decision"]


def test_a_healthy_hermes_run_returns_its_text_and_leaves_a_complete_trace(data):
    seen: list = []
    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), GOOD)
    llm = HermesWriterLLM(direct, runner=hermes_like(seen=seen))
    run_id = trace.start_run()
    response = llm.chat(run_id, "writer", MESSAGES, SPECS)
    assert response.content == GOOD and response.model.startswith("hermes/")
    assert (llm.invocations, llm.fallbacks) == (1, 0)
    kinds = [(e.agent, e.kind) for e in trace.read_run(run_id)]
    assert kinds.count(("writer", "llm_call")) == 2 and ("writer", "tool_call") in kinds  # both upstream calls, the tool run
    assert "cross-check: passed" in decisions(run_id)[-1]
    spec = seen[0]
    assert spec.tools == server.ROLE_TOOLS["writer"] == ("get_brand_brief",)
    assert (spec.system_prompt, spec.user_prompt) == ("You write one post.", "Write the post.")


def test_the_writer_runs_end_to_end_through_hermes_with_harness_owned_fields(data):
    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), GOOD)
    llm = HermesWriterLLM(direct, runner=hermes_like())
    draft = writer.write(llm, trace.start_run(), PLANNED, BRIEF, attempt=2)
    assert isinstance(draft, Draft) and (draft.post_id, draft.attempt) == ("p1", 2) and "flour" in draft.text


def test_a_bad_reply_gets_its_one_repair_on_the_direct_chain_not_hermes(data):
    calls: list = []
    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), "not json at all", GOOD)
    llm = HermesWriterLLM(direct, runner=hermes_like(seen=calls))
    draft = writer.write(llm, trace.start_run(), PLANNED, BRIEF, attempt=1)
    assert draft.text and len(calls) == 1  # Hermes ran once; the repair was a plain chat call
    assert direct.tools_offered[-1] == []  # and, as before, the repair offers no tools


def test_other_roles_never_touch_hermes(data):
    ran: list = []
    direct = script(scores(5))
    llm = HermesWriterLLM(direct, runner=hermes_like(seen=ran))
    draft = Draft(post_id="p1", attempt=1, text="A post.")
    critique = critic.critique(llm, trace.start_run(), draft, PLANNED, BRIEF, 4)
    assert ran == [] and critique.passed and (llm.invocations, llm.fallbacks) == (0, 0)


def test_a_writer_call_without_tools_is_direct(data):
    ran: list = []
    llm = HermesWriterLLM(script(GOOD), runner=hermes_like(seen=ran))
    assert llm.chat(trace.start_run(), "writer", MESSAGES).content == GOOD and ran == []


@pytest.mark.parametrize("runner", [
    hermes_like(log_call=False),  # Hermes says it ran the tool; the MCP server never saw it
    hermes_like(extra_events=[{"type": "tool_use", "name": f"{TOOL_PREFIX}publish_post"}]),  # an unauthorized tool
    hermes_like(exit_code=1),
])
def test_a_run_that_fails_the_cross_check_falls_back_to_direct_once_and_says_so(data, runner):
    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), GOOD, GOOD)
    llm = HermesWriterLLM(direct, runner=runner)
    run_id = trace.start_run()
    response = llm.chat(run_id, "writer", MESSAGES, SPECS)
    assert llm.fallbacks == 1 and response.model == "mock/model:free"  # the direct chain answered the retry
    log = " | ".join(decisions(run_id))
    assert "hermes writer run not trusted" in log and "falling back" in log


def test_a_trace_still_holds_the_untrusted_runs_evidence(data):
    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), GOOD, GOOD)
    llm = HermesWriterLLM(direct, runner=hermes_like(log_call=False, extra_events=[]))
    run_id = trace.start_run()
    llm.chat(run_id, "writer", MESSAGES, SPECS)
    assert any(e.kind == "llm_call" for e in trace.read_run(run_id)[:2])  # the proxy's upstream calls are kept


@pytest.mark.parametrize("error", [HermesRunError("timeout", "no answer"), HermesRunError("hermes_missing", "no hermes")])
def test_a_runner_error_falls_back_to_direct(data, error):
    def runner(spec):
        raise error

    llm = HermesWriterLLM(script(GOOD), runner=runner)
    run_id = trace.start_run()
    assert llm.chat(run_id, "writer", MESSAGES, SPECS).content == GOOD and llm.fallbacks == 1
    assert error.code in " ".join(decisions(run_id))


def test_an_unexpected_message_shape_falls_back_instead_of_guessing(data):
    llm = HermesWriterLLM(script(GOOD), runner=hermes_like())
    odd = [*MESSAGES, {"role": "user", "content": "one more"}]
    assert llm.chat(trace.start_run(), "writer", odd, SPECS).content == GOOD and llm.fallbacks == 1


def test_the_fallback_cannot_exceed_the_shared_attempt_budget(data):
    # Hermes's two proxy requests use the whole budget of 2, so the retry on the direct chain is refused.
    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), GOOD, GOOD)
    budget = Budget(2)
    llm = HermesWriterLLM(direct, runner=hermes_like(log_call=False))
    with pytest.raises(LLMBudgetExceeded):
        llm.chat(trace.start_run(), "writer", MESSAGES, SPECS, budget=budget)
    assert budget.used == 2 and len(direct.calls) == 2


def test_neither_the_proxy_token_nor_the_api_key_reaches_the_trace(data, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-REALKEY1234567890")
    seen: list = []
    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), GOOD)
    run_id = trace.start_run()
    HermesWriterLLM(direct, runner=hermes_like(seen=seen)).chat(run_id, "writer", MESSAGES, SPECS)
    dump = json.dumps([e.model_dump(mode="json") for e in trace.read_run(run_id)])
    assert seen[0].proxy_token not in dump and "REALKEY" not in dump


def test_a_secret_in_hermes_output_makes_the_run_untrusted(data):
    def leaky(spec: HermesSpec) -> HermesResult:
        result = hermes_like()(spec)
        return HermesResult(0, result.final_text, f"debug {spec.proxy_token}", "", result.events)

    direct = script(LLMResponse(model="m:free", content=None, tool_calls=[TOOL_CALL]), GOOD, GOOD)
    llm = HermesWriterLLM(direct, runner=leaky)
    run_id = trace.start_run()
    llm.chat(run_id, "writer", MESSAGES, SPECS)
    assert llm.fallbacks == 1 and "secret_detected" in " ".join(decisions(run_id))


def test_runtime_defaults_to_direct_and_returns_the_client_untouched():
    llm = MockLLM([])
    assert runtime_from_env({}) == "direct" and with_runtime(llm, {}) is llm
    assert with_runtime(llm, {hermes_llm.RUNTIME_ENV: " Direct "}) is llm


def test_hermes_runtime_wraps_the_client():
    llm = MockLLM([])
    wrapped = with_runtime(llm, {hermes_llm.RUNTIME_ENV: "hermes"})
    assert isinstance(wrapped, HermesWriterLLM) and wrapped.direct is llm


def test_an_unknown_runtime_is_refused_not_ignored():
    with pytest.raises(LLMConfigError):
        with_runtime(MockLLM([]), {hermes_llm.RUNTIME_ENV: "hermers"})
