"""Hermes as the writer's runtime, behind the same `LLM` interface every agent already uses.

Only the writer's first call of an attempt (the one that offers its tools) goes through Hermes. The repair call,
and every other role, take the direct chain unchanged, so validation, the one repair (rule 4), the 3-revision cap
(rule 6) and the harness-computed `passed` (rule 5) behave exactly as they do without Hermes. The adapter returns
text; it never publishes and never decides anything.

If a Hermes run cannot be trusted (it timed out, the cross-check disagreed, Hermes is not installed) the
adapter falls back to the direct chain once for that call and records the switch as a decision, so a run is never
lost to the runtime and the trace never hides which one answered.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from harness import trace
from harness.fileio import read_jsonl
from harness.hermes_runner import HermesResult, HermesRunError, HermesSpec, run_hermes
from harness.llm import (DEFAULT_MAX_TOKENS, KEY_ENV, LLM, ROLE_BUDGETS, Budget, LLMConfigError, LLMResponse, Message)
from harness.llm_proxy import LLMProxy
from harness.trace import Agent
from harness.trace_check import Finding, cross_check, ingest_tool_calls
from mcp_server import server

RUNTIME_ENV = "AUTOPILOT_WRITER_RUNTIME"
RUNTIMES = ("direct", "hermes")
# Requests Hermes may make to the proxy in one invocation (the plan's 8/5/2/8); the upstream-attempt budget is
# the role's own, shared with the direct chain.
HERMES_REQUESTS: dict[str, int] = {"planner": 8, "writer": 8, "critic": 2, "analyst": 8}

Runner = Callable[[HermesSpec], HermesResult]


class HermesWriterLLM(LLM):
    def __init__(self, direct: LLM, *, runner: Runner = run_hermes, timeout_s: float | None = None) -> None:
        self.direct = direct
        self._runner = runner
        self._timeout_s = timeout_s
        self.invocations = 0
        self.fallbacks = 0

    def chat(self, run_id: str, agent: Agent, messages: list[Message],
             tools: list[dict[str, Any]] | None = None, *, max_tokens: int = DEFAULT_MAX_TOKENS,
             budget: Budget | None = None) -> LLMResponse:
        if agent != "writer" or not tools:
            return self.direct.chat(run_id, agent, messages, tools, max_tokens=max_tokens, budget=budget)
        try:
            return self._via_hermes(run_id, agent, messages, budget)
        except (HermesRunError, OSError) as e:  # OSError: the proxy could not bind, a temp dir could not be made
            self.fallbacks += 1
            code = e.code if isinstance(e, HermesRunError) else type(e).__name__
            trace.log_event(run_id, agent, "decision", "hermes writer run not trusted",
                            f"{code}: {e}; falling back to the direct chain for this call", ok=False)
            return self.direct.chat(run_id, agent, messages, tools, max_tokens=max_tokens, budget=budget)

    def _via_hermes(self, run_id: str, agent: Agent, messages: list[Message], budget: Budget | None) -> LLMResponse:
        system, user = _split(messages)
        allowed = server.ROLE_TOOLS[agent]
        upstream = budget if budget is not None else Budget(ROLE_BUDGETS[agent])
        self.invocations += 1
        with tempfile.TemporaryDirectory(prefix="autopilot_calls_") as scratch, \
                LLMProxy(self.direct, run_id, agent, max_requests=HERMES_REQUESTS[agent], allowed_tools=allowed,
                          upstream=upstream) as proxy:
            call_log = Path(scratch) / "calls.jsonl"
            spec = HermesSpec(role=agent, system_prompt=system, user_prompt=user, base_url=proxy.base_url,
                              proxy_token=proxy.token, tools=allowed, data_dir=trace.data_dir(), call_log=call_log,
                              **({"timeout_s": self._timeout_s} if self._timeout_s else {}))
            try:
                result = self._runner(spec)
            finally:
                # The tools ran in another process whatever happened to Hermes, so their calls reach the trace
                # even when the run timed out (rule 3).
                mcp_calls, unreadable = read_jsonl(call_log) if call_log.exists() else ([], [])
                ingest_tool_calls(run_id, agent, mcp_calls)
            findings = cross_check(allowed_tools=allowed, result=result, records=proxy.records, mcp_calls=mcp_calls,
                                   secrets=[proxy.token, os.environ.get(KEY_ENV, "")])
            ok_records = [r for r in proxy.records if r.status == 200]
            trace.log_event(
                run_id, agent, "decision", f"hermes {agent} invocation {self.invocations}",
                f"exit={result.exit_code} {result.elapsed_s:.1f}s proxy_requests={len(ok_records)} "
                f"tool_calls={len(mcp_calls)} cross-check: "
                f"{'passed' if not findings else '; '.join(f'{f.code} ({f.detail})' for f in findings)}",
                ok=not findings)
        if unreadable:
            findings.append(Finding("call_log_unreadable", f"{len(unreadable)} unreadable line(s) in the call log"))
        if findings:
            raise HermesRunError(findings[0].code, "; ".join(f.detail for f in findings))
        model = ok_records[-1].model if ok_records else None
        return LLMResponse(model=f"hermes/{model}" if model else "hermes", content=result.final_text,
                           finish_reason="stop", latency_ms=int(result.elapsed_s * 1000))


def _split(messages: list[Message]) -> tuple[str, str]:
    """The writer sends exactly one system and one user message; anything else is not something to guess about."""
    if (len(messages) != 2 or messages[0].get("role") != "system" or messages[1].get("role") != "user"
            or not isinstance(messages[0].get("content"), str) or not isinstance(messages[1].get("content"), str)):
        raise HermesRunError("unsupported_messages", "expected one system and one user message")
    return messages[0]["content"], messages[1]["content"]


def runtime_from_env(env: Mapping[str, str] | None = None) -> str:
    value = (os.environ if env is None else env).get(RUNTIME_ENV, "direct").strip().lower() or "direct"
    if value not in RUNTIMES:
        raise LLMConfigError(f"{RUNTIME_ENV} must be one of {list(RUNTIMES)}, not {value!r}")
    return value


def with_runtime(llm: LLM, env: Mapping[str, str] | None = None) -> LLM:
    """The one place the switch is read. `direct` returns the client untouched, so nothing changes by default."""
    return HermesWriterLLM(llm) if runtime_from_env(env) == "hermes" else llm
