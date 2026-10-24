"""Loopback LLM proxy: the only thing that holds the API key when Hermes runs a role.

Hermes is pointed at this server instead of OpenRouter. That buys three things the harness needs:
the key never enters a Hermes config (Hermes backs its config up to disk), every upstream attempt is
traced by the same `LLM.chat` the direct path uses (Hermes's own hooks miss the summary calls it makes
after an iteration limit), and the request budget is enforced on our side of the wire, so a looping
agent cannot drain the free daily quota (architecture rule 6, decision 4.4).

It forwards through an `LLM`, never straight to a URL, so the free-model check, backoff, fallback and
dead-model skipping stay in one place. Anything unexpected is refused with a 403, which Hermes treats
as non-retryable: failing closed beats a retry that spends more quota.
"""

from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any

from harness import trace
from harness.hermes_runner import TOOL_PREFIX
from harness.llm import DEFAULT_MAX_TOKENS, LLM, Budget, LLMError, LLMResponse
from harness.trace import Agent

HOST = "127.0.0.1"
MAX_BODY_BYTES = 2_000_000
MAX_DRAIN_BYTES = 8_000_000  # read and discard this much of an oversized body, so the refusal is delivered
CHAT_PATH = "/v1/chat/completions"


@dataclass(frozen=True)
class ProxyRecord:
    """One request Hermes made, kept so the harness can check what Hermes was offered and what it got."""

    tools: tuple[str, ...]
    status: int
    model: str | None = None
    reason: str = ""
    called: tuple[str, ...] = ()  # tool names the model asked for in this reply, for the cross-check
    reply: str = ""  # the text the model returned, so Hermes's final answer can be tied back to a real model reply


@dataclass
class LLMProxy:
    """One proxy per Hermes invocation: a role, a request cap and an upstream-attempt budget."""

    llm: LLM
    run_id: str
    role: Agent
    max_requests: int
    # Bare tool names the role may be offered. Required, so a caller cannot forget it: the proxy refuses any other
    # tool before the model sees it, instead of leaving the cross-check to notice after the call has run.
    allowed_tools: tuple[str, ...]
    upstream: Budget | None = None
    # A per-run bearer token, so another local process that finds the port cannot spend this run's quota.
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    records: list[ProxyRecord] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = field(default=None, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _gate: Budget = field(init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        # Every upstream attempt is charged through this child of the run's budget. stop() empties it, which is how
        # a handler still inside LLM.chat when Hermes is killed is kept from taking one more attempt.
        self._gate = Budget(10**9, parent=self.upstream)

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("proxy is not running")
        return f"http://{HOST}:{self._server.server_port}/v1"

    def __enter__(self) -> LLMProxy:
        self.start()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.stop()

    def start(self) -> None:
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # the default writes every request to stderr
                pass

            def _send(self, status: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _authorized(self) -> bool:
                # Bytes, because compare_digest raises on a non-ASCII str and a dead handler thread resets the client.
                sent = self.headers.get("Authorization", "").encode("utf-8", "replace")
                return secrets.compare_digest(sent, f"Bearer {proxy.token}".encode())

            def do_GET(self) -> None:
                # Hermes probes /v1/models for context sizes; an empty list is a valid answer and costs nothing.
                if not self._authorized():
                    return self._send(401, {"error": {"message": "bad token"}})
                self._send(200, {"object": "list", "data": []})

            def _read_body(self) -> bytes | None:
                """The body, or None when it is missing or too big to trust.

                Whatever the client sent is consumed (up to MAX_DRAIN_BYTES) even when the answer is a refusal:
                replying with unread data in the socket makes Windows reset the connection, and the client then
                sees a network error instead of our 401 or 400.
                """
                try:
                    length = int(self.headers.get("Content-Length", 0))
                except ValueError:
                    return None
                keep = 0 < length <= MAX_BODY_BYTES
                chunks: list[bytes] = []
                remaining = min(max(length, 0), MAX_DRAIN_BYTES)
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    if keep:
                        chunks.append(chunk)
                return b"".join(chunks) if keep else None

            def do_POST(self) -> None:
                raw = self._read_body()
                if not self._authorized():
                    return self._send(401, {"error": {"message": "bad token"}})
                if self.path.split("?")[0] != CHAT_PATH:
                    return self._send(404, {"error": {"message": "not found"}})
                try:
                    if raw is None:
                        raise ValueError("body missing or too large")
                    body = json.loads(raw)
                    if not isinstance(body, dict):
                        raise ValueError("body is not an object")
                except ValueError:
                    return self._send(400, {"error": {"message": "invalid request body"}})
                status, payload = proxy.handle_chat(body)
                self._send(status, payload)

        self._server = ThreadingHTTPServer((HOST, 0), Handler)
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def stop(self) -> None:
        """Close for good. A handler already inside LLM.chat cannot be interrupted, but it can be stopped from taking
        another attempt or answering a new request, so a killed Hermes run cannot go on spending the shared budget
        while the fallback runs."""
        self._closed = True
        self._gate.limit = 0
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def handle_chat(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Forward one chat request through the chain. Serialised, so the budgets are exact."""
        tools = body.get("tools") if isinstance(body.get("tools"), list) else None
        names = tuple(sorted(_tool_name(t) for t in tools or []))
        messages = body.get("messages")
        with self._lock:
            refusal = self._refusal(body, messages, names)
            if refusal is not None:
                return self._refuse(names, *refusal)
            try:
                response = self.llm.chat(self.run_id, self.role, messages, tools or None,
                                         max_tokens=DEFAULT_MAX_TOKENS, budget=self._gate)
            except LLMError as e:
                return self._refuse(names, 403, f"{type(e).__name__}: {e}")
            except Exception as e:  # noqa: BLE001 - fail closed: a trace write error must not become a retry
                return self._refuse(names, 403, f"proxy error: {type(e).__name__}")
            self.records.append(ProxyRecord(names, 200, response.model,
                                            called=tuple(_call_name(c) for c in response.tool_calls),
                                            reply=response.content or ""))
            return 200, _completion(response)

    def _refusal(self, body: dict[str, Any], messages: Any, offered: tuple[str, ...]) -> tuple[int, str] | None:
        """(status, reason) for a request to turn away before any upstream call. 400 is the caller's mistake and
        403 is our limit; both are non-retryable for Hermes."""
        if self._closed:
            return 403, "proxy is closed"
        allowed = {f"{TOOL_PREFIX}{t}" for t in self.allowed_tools}
        outside = [n for n in offered if n not in allowed]
        if outside:
            return 403, f"tool not allowed for the {self.role} role: {outside}"  # rule 7, before the model sees it
        if body.get("stream"):
            return 400, "stream: true is not supported"  # the harness reads whole replies; Hermes is set not to stream
        if not isinstance(messages, list) or not messages:
            return 400, "messages must be a non-empty list"
        if sum(1 for r in self.records if r.status == 200) >= self.max_requests:
            return 403, f"request budget of {self.max_requests} used up"
        return None

    def _refuse(self, names: tuple[str, ...], status: int, reason: str) -> tuple[int, dict[str, Any]]:
        self.records.append(ProxyRecord(names, status, reason=reason))
        trace.log_event(self.run_id, self.role, "decision", "hermes request refused", f"proxy {status}: {reason}",
                        ok=False)
        return status, {"error": {"message": reason, "type": "autopilot_proxy_refusal", "code": status}}


def _tool_name(spec: Any) -> str:
    fn = spec.get("function") if isinstance(spec, dict) else None
    return str(fn.get("name")) if isinstance(fn, dict) else "?"


def _call_name(call: Any) -> str:
    fn = call.get("function") if isinstance(call, dict) else None
    return str(fn.get("name")) if isinstance(fn, dict) else "?"


def _completion(r: LLMResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": r.content}
    if r.tool_calls:
        message["tool_calls"] = r.tool_calls
    finish = r.finish_reason or ("tool_calls" if r.tool_calls else "stop")
    prompt, completion = r.prompt_tokens or 0, r.completion_tokens or 0
    return {"id": f"autopilot-{secrets.token_hex(6)}", "object": "chat.completion", "model": r.model,
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}}
