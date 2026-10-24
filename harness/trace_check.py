"""Cross-check one Hermes invocation against three independent records, and fail closed on any disagreement.

Hermes is a process we do not control, so its own account of a run is not evidence on its own. Three sources
see the same run from different places: the proxy (what the model asked for and was offered), Hermes's stream
(what it says it ran) and the MCP server's call log (what actually executed, with receipts a model cannot
guess). A tool that appears in one but not the others, a tool outside the role's allowlist, a refused or cut-off
run, or a secret in the output all make the run untrustworthy (architecture rules 3 and 7).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from harness import trace
from harness.hermes_runner import TOOL_PREFIX, HermesResult
from harness.llm_proxy import ProxyRecord
from harness.trace import Agent

_KEY_SHAPE = re.compile(r"sk-or-[A-Za-z0-9_\-]+")
_MIN_SECRET_LEN = 8


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str


def _names(events: Iterable[dict[str, Any]], kind: str) -> list[str]:
    return [str(e.get("name")) for e in events if e.get("type") == kind]


def cross_check(*, allowed_tools: Sequence[str], result: HermesResult, records: Sequence[ProxyRecord],
                mcp_calls: Sequence[dict[str, Any]], secrets: Iterable[str] = ()) -> list[Finding]:
    """Every reason not to trust this run; empty means the three records agree."""
    findings: list[Finding] = []
    allowed = {f"{TOOL_PREFIX}{t}" for t in allowed_tools}

    if result.exit_code != 0:
        findings.append(Finding("exit_failed", f"hermes exited {result.exit_code}"))
    if result.final_text is None:
        findings.append(Finding("stream_incomplete", "the stream had no closing result event"))
    if not records:
        findings.append(Finding("llm_unmatched", "hermes ran without one request reaching the proxy"))
    refused = [r for r in records if r.status != 200]
    if refused:
        findings.append(Finding("proxy_refused", "; ".join(f"{r.status}: {r.reason}" for r in refused)))

    last_reply = next((r for r in reversed(records) if r.status == 200), None)
    # Contained, not equal: Hermes may strip a reasoning block or whitespace, but it cannot invent a post.
    if result.final_text is not None and last_reply is not None and result.final_text.strip() not in last_reply.reply:
        findings.append(Finding("final_text_mismatch", "hermes's final text is not in the last model reply"))

    offered = {name for r in records for name in r.tools}
    streamed = _names(result.events, "tool_use")
    asked = [name for r in records for name in r.called]
    executed = [f"{TOOL_PREFIX}{c.get('tool')}" for c in mcp_calls]
    outside = sorted((offered | set(streamed) | set(asked) | set(executed)) - allowed)
    if outside:
        findings.append(Finding("tool_unauthorized", f"outside the allowlist: {outside}"))
    if not Counter(asked) == Counter(streamed) == Counter(executed):
        findings.append(Finding("tool_mismatch", f"model asked {sorted(asked)}, hermes ran {sorted(streamed)}, "
                                                 f"the server executed {sorted(executed)}"))

    haystack = "\n".join([result.stdout, result.stderr, result.final_text or ""])
    needles = [s for s in secrets if len(s) >= _MIN_SECRET_LEN]
    if any(s in haystack for s in needles) or _KEY_SHAPE.search(haystack):
        findings.append(Finding("secret_detected", "a credential appeared in hermes output"))
    return findings


def ingest_tool_calls(run_id: str, role: Agent, mcp_calls: Sequence[dict[str, Any]]) -> None:
    """Copy the server's executed calls into the run trace: they ran in another process, so nothing else would."""
    for call in mcp_calls:
        trace.log_event(run_id, role, "tool_call", f"{call.get('tool')} | {call.get('args')} (via hermes)",
                        f"receipt {call.get('receipt')}: {call.get('result')}", ok=bool(call.get("ok")),
                        latency_ms=call.get("latency_ms"))
