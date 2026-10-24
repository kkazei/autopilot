"""The loopback proxy Hermes talks to: it must forward through the chain, hold every budget and fail closed.

Everything runs against MockLLM over loopback, so no test here can spend quota.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import pytest

from harness import trace
from harness.llm import (Budget, LLMAuthError, LLMBudgetExceeded, LLMResponse, LLMUnavailable, MockLLM)
from harness.llm_proxy import LLMProxy
from tests.helpers import data  # noqa: F401 - fixture

MESSAGES = [{"role": "user", "content": "Write the post."}]
TOOL = {"type": "function", "function": {"name": "mcp__autopilot__get_brand_brief", "parameters": {}}}


def post(proxy: LLMProxy, body: dict[str, Any], *, token: str | None = None, path: str = "/chat/completions",
         raw: bytes | None = None) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        proxy.base_url + path, data=raw if raw is not None else json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {proxy.token if token is None else token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def make(data, script, **kwargs) -> tuple[LLMProxy, MockLLM]:
    llm = MockLLM(script)
    defaults = {"max_requests": 8, "allowed_tools": ("get_brand_brief",)}
    return LLMProxy(llm, trace.start_run(), "writer", **{**defaults, **kwargs}), llm


def events(proxy: LLMProxy) -> list:
    return trace.read_run(proxy.run_id)


def test_forwards_a_chat_request_and_traces_the_upstream_call(data):
    proxy, llm = make(data, ['{"text": "hi"}'])
    with proxy:
        status, body = post(proxy, {"model": "ignored/by-the-proxy", "messages": MESSAGES})
    assert status == 200
    assert body["choices"][0]["message"] == {"role": "assistant", "content": '{"text": "hi"}'}
    assert body["choices"][0]["finish_reason"] == "stop"
    assert llm.calls == [MESSAGES]  # the model name Hermes asked for is not used: the chain decides
    assert [e.kind for e in events(proxy)] == ["llm_call"] and events(proxy)[0].agent == "writer"


def test_tool_calls_pass_through_in_the_openai_shape(data):
    call = {"id": "c1", "type": "function", "function": {"name": "mcp__autopilot__get_brand_brief", "arguments": "{}"}}
    proxy, llm = make(data, [LLMResponse(model="m:free", content=None, tool_calls=[call])])
    with proxy:
        status, body = post(proxy, {"messages": MESSAGES, "tools": [TOOL]})
    choice = body["choices"][0]
    assert status == 200 and choice["message"]["tool_calls"] == [call] and choice["finish_reason"] == "tool_calls"
    assert llm.tools_offered == [["mcp__autopilot__get_brand_brief"]]
    assert proxy.records[0].tools == ("mcp__autopilot__get_brand_brief",)


def test_a_request_without_the_run_token_is_refused_before_any_upstream_call(data):
    proxy, llm = make(data, ["x"])
    with proxy:
        status, _ = post(proxy, {"messages": MESSAGES}, token="not-the-token")
    assert status == 401 and llm.calls == [] and proxy.records == []


def test_streaming_is_refused_and_costs_nothing(data):
    proxy, llm = make(data, ["x"])
    with proxy:
        status, body = post(proxy, {"messages": MESSAGES, "stream": True})
    assert status == 400 and "stream" in body["error"]["message"] and llm.calls == []
    assert events(proxy)[0].ok is False


@pytest.mark.parametrize("raw", [b"not json", b"[]", b""])
def test_a_malformed_body_is_a_400(data, raw):
    proxy, llm = make(data, ["x"])
    with proxy:
        status, _ = post(proxy, {}, raw=raw)
    assert status == 400 and llm.calls == []


def test_missing_messages_is_a_400(data):
    proxy, llm = make(data, ["x"])
    with proxy:
        status, _ = post(proxy, {"messages": []})
    assert status == 400 and llm.calls == []


def test_the_request_cap_stops_hermes_with_a_403_and_makes_no_extra_upstream_call(data):
    proxy, llm = make(data, ["a", "b", "c"], max_requests=2)
    with proxy:
        statuses = [post(proxy, {"messages": MESSAGES})[0] for _ in range(3)]
    assert statuses == [200, 200, 403] and len(llm.calls) == 2
    assert "request budget of 2" in events(proxy)[-1].summary_out


def test_a_failed_upstream_request_does_not_use_up_the_request_cap(data):
    proxy, llm = make(data, [LLMUnavailable("all models failed"), "ok"], max_requests=1)
    with proxy:
        first, _ = post(proxy, {"messages": MESSAGES})
        second, _ = post(proxy, {"messages": MESSAGES})
    assert (first, second) == (403, 200)


def test_the_upstream_attempt_budget_is_shared_with_the_run(data):
    budget = Budget(1)
    proxy, llm = make(data, ["a", "b"], upstream=budget)
    with proxy:
        statuses = [post(proxy, {"messages": MESSAGES})[0] for _ in range(2)]
    assert statuses == [200, 403] and budget.used == 1 and len(llm.calls) == 1


@pytest.mark.parametrize("error", [LLMUnavailable("all 3 models failed"), LLMAuthError("HTTP 401"),
                                   LLMBudgetExceeded("writer: budget used up"), trace.TraceWriteError("disk full")])
def test_every_upstream_failure_is_a_non_retryable_403(data, error):
    proxy, _ = make(data, [error])
    with proxy:
        status, body = post(proxy, {"messages": MESSAGES})
    assert status == 403 and body["error"]["type"] == "autopilot_proxy_refusal"


def test_an_unexpected_exception_fails_closed_and_leaks_no_detail(data):
    proxy, _ = make(data, [RuntimeError("secret detail sk-or-v1-abc")])
    with proxy:
        status, body = post(proxy, {"messages": MESSAGES})
    assert status == 403 and "secret detail" not in json.dumps(body)


def test_unknown_paths_are_404_and_models_probe_is_free(data):
    proxy, llm = make(data, ["x"])
    with proxy:
        assert post(proxy, {"messages": MESSAGES}, path="/embeddings")[0] == 404
        request = urllib.request.Request(proxy.base_url + "/models", headers={"Authorization": f"Bearer {proxy.token}"})
        with urllib.request.urlopen(request, timeout=10) as r:
            assert json.loads(r.read()) == {"object": "list", "data": []}
    assert llm.calls == []


def test_the_proxy_only_listens_on_loopback_and_stops_cleanly(data):
    proxy, _ = make(data, [])
    with proxy:
        assert proxy.base_url.startswith("http://127.0.0.1:")
    with pytest.raises(RuntimeError):
        _ = proxy.base_url


def test_the_run_token_is_unique_per_proxy_and_never_traced(data):
    first, _ = make(data, ["x"])
    second, _ = make(data, ["x"])
    assert first.token != second.token and len(first.token) >= 24
    with first:
        post(first, {"messages": MESSAGES})
    assert first.token not in json.dumps([e.model_dump(mode="json") for e in events(first)])


def test_an_oversized_body_is_refused_before_it_is_read_or_forwarded(data):
    proxy, llm = make(data, ["x"])
    padded = {"messages": MESSAGES, "padding": "x" * 2_100_000}  # valid JSON, just too big to trust
    with proxy:
        status, _ = post(proxy, padded)
    assert status == 400 and llm.calls == []


@pytest.mark.parametrize("offered", [
    ["terminal"],  # a Hermes built-in that must never reach the model
    ["mcp__autopilot__get_brand_brief", "mcp__autopilot__publish_post"],  # one good name does not excuse a bad one
    ["mcp__autopilot__get_brand_brief_extra"],  # a lookalike, not a prefix match
    ["get_brand_brief"],  # the bare name is not what Hermes sends for an MCP tool
])
def test_a_tool_outside_the_roles_allowlist_is_refused_before_any_upstream_call(data, offered):
    proxy, llm = make(data, ["x"])
    tools = [{"type": "function", "function": {"name": n}} for n in offered]
    with proxy:
        status, body = post(proxy, {"messages": MESSAGES, "tools": tools})
    assert status == 403 and "not allowed" in body["error"]["message"] and llm.calls == []
    assert proxy.records[0].status == 403


def test_a_role_with_no_tools_is_refused_any_tool_at_all(data):
    proxy, llm = make(data, ["x"], allowed_tools=())
    with proxy:
        status, _ = post(proxy, {"messages": MESSAGES, "tools": [TOOL]})
        ok, _ = post(proxy, {"messages": MESSAGES})
    assert (status, ok) == (403, 200) and len(llm.calls) == 1


def test_a_non_ascii_authorization_header_is_a_401_not_a_dead_handler(data):
    proxy, llm = make(data, ["x"])
    with proxy:
        host, port = proxy.base_url.split("//")[1].split("/")[0].split(":")
        conn = http.client.HTTPConnection(host, int(port), timeout=5)
        conn.putrequest("POST", "/v1/chat/completions")
        conn.putheader("Authorization", "Bearer café")
        conn.putheader("Content-Length", "2")
        conn.endheaders(b"{}")
        assert conn.getresponse().status == 401
    assert llm.calls == []


class SlowLLM(MockLLM):
    """Answers only after a delay, like a free model stuck in backoff when Hermes is killed."""

    def chat(self, *args, **kwargs):
        time.sleep(1.0)
        return super().chat(*args, **kwargs)


def test_a_request_in_flight_when_the_proxy_stops_cannot_spend_the_budget_afterwards(data):
    budget = Budget(5)
    llm = SlowLLM(["late"])
    proxy = LLMProxy(llm, trace.start_run(), "writer", max_requests=8, allowed_tools=("get_brand_brief",),
                     upstream=budget)
    proxy.start()
    late = threading.Thread(target=lambda: post(proxy, {"messages": MESSAGES}), daemon=True)
    late.start()
    time.sleep(0.3)  # the handler is now inside the slow upstream call
    proxy.stop()
    late.join(10)
    time.sleep(0.2)
    assert budget.used == 0 and llm.calls == [], "a handler kept spending after stop()"


def test_a_stopped_proxy_refuses_late_requests_without_charging_anything(data):
    budget = Budget(5)
    proxy, llm = make(data, ["x"], upstream=budget)
    proxy.start()
    proxy.stop()
    status, body = proxy.handle_chat({"messages": MESSAGES})
    assert status == 403 and body["error"]["message"] == "proxy is closed"  # named, so the trace says why
    assert budget.used == 0 and llm.calls == []
