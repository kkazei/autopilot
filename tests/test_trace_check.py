"""harness/trace_check.py: the three records of a Hermes run must agree, and any gap is a named finding."""

from __future__ import annotations

import pytest

from harness import trace
from harness.hermes_runner import TOOL_PREFIX, HermesResult
from harness.llm_proxy import ProxyRecord
from harness.trace_check import cross_check, ingest_tool_calls
from tests.helpers import data  # noqa: F401 - fixture

BRIEF = f"{TOOL_PREFIX}get_brand_brief"
ALLOWED = ("get_brand_brief",)


def result(*, exit_code=0, text="{}", events=None, stdout="", stderr="") -> HermesResult:
    stream = [{"type": "tool_use", "name": BRIEF}, {"type": "result", "text": text}] if events is None else events
    return HermesResult(exit_code, text, stdout, stderr, tuple(stream))


def records(*, called=(BRIEF,), tools=(BRIEF,), status=200, reply="{}"):
    return [ProxyRecord(tuple(tools), status, "m:free", called=tuple(called)),
            ProxyRecord(tuple(tools), 200, "m:free", reply=reply)]


def mcp(*names):
    return [{"tool": n, "receipt": f"r{i}", "ok": True, "args": "{}", "result": "{}", "latency_ms": 1}
            for i, n in enumerate(names)]


def codes(**kwargs) -> list[str]:
    base = dict(allowed_tools=ALLOWED, result=result(), records=records(), mcp_calls=mcp("get_brand_brief"))
    return [f.code for f in cross_check(**{**base, **kwargs})]


def test_three_agreeing_records_pass():
    assert codes() == []


def test_a_run_that_calls_no_tool_at_all_also_agrees():
    assert codes(result=result(events=[{"type": "result", "text": "{}"}]), records=records(called=()),
                 mcp_calls=[]) == []


def test_a_failed_exit_is_a_finding():
    assert "exit_failed" in codes(result=result(exit_code=1))


def test_a_stream_without_a_closing_result_is_incomplete():
    cut = HermesResult(0, None, "", "", ({"type": "tool_use", "name": BRIEF},))
    assert "stream_incomplete" in codes(result=cut)


def test_hermes_that_never_reached_the_proxy_is_unmatched():
    assert "llm_unmatched" in codes(records=[])


def test_a_refused_proxy_request_is_a_finding():
    found = cross_check(allowed_tools=ALLOWED, result=result(), mcp_calls=mcp("get_brand_brief"),
                        records=[ProxyRecord((BRIEF,), 403, reason="request budget of 8 used up")])
    assert any(f.code == "proxy_refused" and "budget" in f.detail for f in found)


@pytest.mark.parametrize("where", ["offered", "streamed", "asked", "executed"])
def test_a_tool_outside_the_allowlist_is_caught_in_any_one_record(where):
    bad = f"{TOOL_PREFIX}publish_post"
    kwargs = {}
    if where == "offered":
        kwargs["records"] = records(tools=(BRIEF, bad))
    elif where == "streamed":
        kwargs["result"] = result(events=[{"type": "tool_use", "name": bad}, {"type": "result", "text": "{}"}])
    elif where == "asked":
        kwargs["records"] = records(called=(bad,))
    else:
        kwargs["mcp_calls"] = mcp("publish_post")
    assert "tool_unauthorized" in codes(**kwargs)


@pytest.mark.parametrize("kwargs", [
    {"mcp_calls": []},  # Hermes says it ran a tool the server never saw
    {"mcp_calls": mcp("get_brand_brief", "get_brand_brief")},  # the server ran one more than was asked for
    {"records": records(called=())},  # a call the model never asked for
])
def test_any_disagreement_between_the_three_records_is_a_mismatch(kwargs):
    assert "tool_mismatch" in codes(**kwargs)


@pytest.mark.parametrize("field", ["stdout", "stderr", "text"])
def test_a_secret_anywhere_in_the_output_is_caught(field):
    out = {"stdout": "", "stderr": "", "text": "{}"}
    out[field] = "leaked run-token-abcdefghijklmnop here"
    assert "secret_detected" in codes(result=result(**out), secrets=["run-token-abcdefghijklmnop"])


def test_a_key_shaped_string_is_caught_even_when_it_is_not_a_known_secret():
    assert "secret_detected" in codes(result=result(stdout="key sk-or-v1-abcdef123456"))


def test_short_secrets_are_ignored_so_an_empty_env_var_cannot_match_everything():
    assert codes(secrets=["", "abc"]) == []


def test_every_finding_is_reported_not_just_the_first():
    assert set(codes(result=result(exit_code=2), records=[], mcp_calls=[])) >= {"exit_failed", "llm_unmatched"}


def test_executed_calls_are_copied_into_the_run_trace(data):
    run_id = trace.start_run()
    ingest_tool_calls(run_id, "writer", mcp("get_brand_brief"))
    event = trace.read_run(run_id)[0]
    assert (event.kind, event.agent, event.ok) == ("tool_call", "writer", True)
    assert "get_brand_brief" in event.summary_in and "via hermes" in event.summary_in and "r0" in event.summary_out


def test_final_text_that_no_model_produced_is_a_finding():
    assert "final_text_mismatch" in codes(result=result(text="a post nobody wrote"), records=records(reply='{"text": "x"}'))


@pytest.mark.parametrize("final", ['{"text": "x"}', '  {"text": "x"}\n'])
def test_final_text_matching_the_last_reply_passes_even_with_whitespace_differences(final):
    assert codes(result=result(text=final), records=records(reply='{"text": "x"}\n')) == []


def test_hermes_may_strip_reasoning_from_the_reply_it_reports():
    reply = '<think>let me see</think>{"text": "x"}'
    assert codes(result=result(text='{"text": "x"}'), records=records(reply=reply)) == []
