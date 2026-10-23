"""LLM access for every role: one ordered chain of free OpenRouter models, with bounded fallback.

Free models fail often and differently (a 429 from a shared pool clears in seconds, a 404 for a
retired endpoint never does), so each failure is classified: transient errors back off and retry
the same model a bounded number of times, a dead model is skipped at once, and an auth or billing
error stops the run, because no other model would fix it and falling back would hide it.

Every upstream attempt is an `llm_call` trace event, and every backoff and fallback a `decision`
event, so the trace shows exactly which model answered and why the others did not.
Standard library only: urllib is enough for one JSON POST, and fewer dependencies means less to
audit. The key lives only in the request header and is never logged; the trace also redacts it.
"""

from __future__ import annotations

import json
import os
import random
import re
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from harness import trace
from harness.trace import Agent

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_ENV = "OPENROUTER_API_KEY"
MODELS_ENV = "OPENROUTER_MODELS"
FREE_SUFFIX = ":free"
MAX_TRIES_PER_MODEL = 3
TIMEOUT_S = 120.0
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 30.0
DEFAULT_MAX_TOKENS = 4096  # free models still cost $0; reasoning models used ~990 of 1,024 thinking (run_..._d8f068)

FATAL_STATUSES = frozenset({401, 402, 403})
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

T = TypeVar("T", bound=BaseModel)
Message = dict[str, Any]


class LLMError(RuntimeError):
    """Base class, so callers can fail one step cleanly without catching unrelated errors."""


class LLMConfigError(LLMError):
    """Missing key or models, or a model id that is not free: refused before any request is sent."""


class LLMAuthError(LLMError):
    """401/402/403. Never falls back: every model shares the key, so the next one would fail the same way."""


class LLMUnavailable(LLMError):
    """Every model in the chain failed; the caller escalates instead of retrying forever."""


class LLMBudgetExceeded(LLMUnavailable):
    """The invocation used up its upstream-attempt budget (decision 4.4); handled like an unavailable chain."""


class LLMOutputError(LLMError):
    """The answer was still invalid after the one repair attempt (architecture rule 4)."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str


Transport = Callable[[str, Mapping[str, str], bytes, float], HttpResponse]


def urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout_s: float) -> HttpResponse:
    """HTTP errors come back as responses (the chain classifies them); a timeout raises TimeoutError."""
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as r:
            return HttpResponse(r.status, r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise TimeoutError(f"no response within {timeout_s}s") from None
        raise ConnectionError(f"network error: {e.reason}") from None
    except socket.timeout:
        raise TimeoutError(f"no response within {timeout_s}s") from None


@dataclass(frozen=True)
class LLMResponse:
    model: str
    content: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int = 0


@dataclass(frozen=True)
class _Failure:
    """One failed attempt. `kind` decides what happens next: retry, skip or stop."""

    kind: str  # "transient" | "skip" | "dead" | "fatal"
    reason: str


def models_from_env(env: Mapping[str, str] | None = None) -> list[str]:
    """The chain comes from one place (OPENROUTER_MODELS) and refuses any paid id, so a typo can never cost money."""
    raw = (os.environ if env is None else env).get(MODELS_ENV, "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    if not models:
        raise LLMConfigError(f"{MODELS_ENV} is empty")
    paid = [m for m in models if not m.endswith(FREE_SUFFIX)]
    if paid:
        raise LLMConfigError(f"refusing non-free model ids: {paid}")
    return models


def classify_status(status: int) -> str:
    if status in FATAL_STATUSES:
        return "fatal"
    if status == 429 or status >= 500:
        return "transient"
    if status == 404:
        return "dead"  # a retired endpoint (minimax :free on Oct 22) stays gone, so it is not asked again this run
    return "skip"  # 400 (model rejects the request) and other 4xx: another model may work, and may accept the next call


def parse_completion(model: str, body: str, latency_ms: int) -> LLMResponse | _Failure:
    """OpenRouter sometimes returns 200 with an upstream error inside, so a 200 is not trusted on its own."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return _Failure("transient", "200 with a non-JSON body")
    if not isinstance(data, dict):
        return _Failure("transient", "200 with a non-object body")
    if "error" in data:
        err = data["error"] if isinstance(data["error"], dict) else {}
        code = err.get("code")
        status = code if isinstance(code, int) else 502
        return _Failure(classify_status(status), f"HTTP {status} (in a 200 body): {err.get('message', '')}")
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return _Failure("transient", "200 with no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    tool_calls = message.get("tool_calls") or []
    finish = choices[0].get("finish_reason")
    usage = data.get("usage") or {}
    # Kept on failures too: an empty or cut-off reply is only diagnosable with its finish reason and token counts.
    stats = f"finish={finish} tokens in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}"
    if finish == "length":
        # A reasoning model can spend the whole budget thinking and stop mid-JSON. The same model with the
        # same limit is likely to do it again, so this is a skip to the next model, not a retry.
        return _Failure("skip", f"truncated at max_tokens ({stats})")
    if not (isinstance(content, str) and content.strip()) and not tool_calls:
        return _Failure("transient", f"200 with an empty message ({stats})")
    return LLMResponse(
        model=data.get("model") or model,
        content=content if isinstance(content, str) else None,
        tool_calls=list(tool_calls),
        finish_reason=finish,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        latency_ms=latency_ms,
    )


def extract_json(text: str) -> str:
    """Free models often wrap JSON in a code fence or a sentence; take the outermost object rather than fail on it."""
    text = text.strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def _describe(response: LLMResponse) -> str:
    out = response.content or json.dumps(response.tool_calls, ensure_ascii=False)
    return (f"tokens in={response.prompt_tokens} out={response.completion_tokens} "
            f"finish={response.finish_reason}: {out}")


@dataclass
class Budget:
    """Upstream attempts left for one agent invocation (decision 4.4), shared by its tool rounds and its repair,
    so one stubborn post cannot drain the free daily quota.

    A budget may have a parent (the whole run, or the run's measurement phase): every attempt is charged to
    each level, so no single agent budget can push a run past its own cap.
    """

    limit: int
    used: int = 0
    parent: Budget | None = None

    def exhausted_by(self) -> Budget | None:
        """The innermost budget with nothing left, or None while every level still has attempts."""
        if self.used >= self.limit:
            return self
        return self.parent.exhausted_by() if self.parent is not None else None

    def take(self) -> bool:
        """Charge one attempt to this budget and every parent, or charge none of them."""
        if self.exhausted_by() is not None:
            return False
        budget: Budget | None = self
        while budget is not None:
            budget.used += 1
            budget = budget.parent
        return True


def _budget_error(agent: str, budget: Budget) -> LLMBudgetExceeded:
    blocker = budget.exhausted_by() or budget
    return LLMBudgetExceeded(f"{agent}: upstream attempt budget of {blocker.limit} used up")


ROLE_BUDGETS: dict[str, int] = {"planner": 12, "writer": 8, "critic": 4, "analyst": 12}
MAX_TOOL_ROUNDS = 2

ToolRunner = Callable[[str, dict[str, Any]], str]


class LLM(ABC):
    """Shared by the real client and MockLLM, so agents and tests take the same code path for tools, validation and repair."""

    @abstractmethod
    def chat(self, run_id: str, agent: Agent, messages: list[Message],
             tools: list[dict[str, Any]] | None = None, *, max_tokens: int = DEFAULT_MAX_TOKENS,
             budget: Budget | None = None) -> LLMResponse:
        """Return the first good answer from the chain, or raise an LLMError."""

    def chat_json(self, run_id: str, agent: Agent, messages: list[Message], schema: type[T],
                  *, tools: list[dict[str, Any]] | None = None, run_tool: ToolRunner | None = None,
                  overrides: Mapping[str, Any] | None = None, budget: Budget | None = None,
                  repair_hint: str = "", max_tokens: int = DEFAULT_MAX_TOKENS) -> T:
        """Validate the answer against `schema`; on failure, show the model its errors once, then give up (rule 4).

        `overrides` are the fields the harness owns (post_id, attempt, ...): they replace whatever the model sent
        before validation, so a model can neither fake them nor fail validation for leaving them out.
        """
        messages = list(messages)
        response = self.chat(run_id, agent, messages, tools, max_tokens=max_tokens, budget=budget)
        rounds = 0
        while response.tool_calls and tools and run_tool and rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            messages.append({"role": "assistant", "content": response.content or "", "tool_calls": response.tool_calls})
            for call in response.tool_calls:
                fn = call.get("function") or {}
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "content": run_tool(str(fn.get("name")), _tool_args(fn.get("arguments")))})
            response = self.chat(run_id, agent, messages, tools, max_tokens=max_tokens, budget=budget)
        first = _validated(response, schema, overrides)
        if isinstance(first, BaseModel):
            return first
        error = first
        trace.log_event(run_id, agent, "decision", f"invalid {schema.__name__} from {response.model}",
                        f"repair attempt: {error}", ok=False, model=response.model)
        # The repair goes out without tools, so the model has to answer in text this time.
        repair = [*messages,
                  {"role": "assistant", "content": response.content or ""},
                  {"role": "user", "content": repair_prompt(schema.__name__, error, repair_hint)}]
        repaired = self.chat(run_id, agent, repair, max_tokens=max_tokens, budget=budget)
        result = _validated(repaired, schema, overrides)
        if isinstance(result, BaseModel):
            trace.log_event(run_id, agent, "decision", f"repair of {schema.__name__}", "repair succeeded",
                            ok=True, model=repaired.model)
            return result
        trace.log_event(run_id, agent, "decision", f"repair of {schema.__name__}", f"repair failed: {result}",
                        ok=False, model=repaired.model)
        raise LLMOutputError(f"{agent}: invalid {schema.__name__} after one repair attempt: {result}")


def repair_prompt(schema_name: str, error: str, hint: str = "") -> str:
    """Short and explicit: the cut-off repair in run_..._d8f068 came from a model thinking at length before answering."""
    return "\n".join(line for line in (
        f"Your reply was not a valid {schema_name} JSON object. Errors: {error}",
        hint,
        "Do not explain or think aloud. Reply with only the corrected JSON object, no other text.",
    ) if line)


def _tool_args(raw: Any) -> dict[str, Any]:
    """Bad arguments become an empty call that the tool can refuse, instead of a crash in the loop."""
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _validated(response: LLMResponse, schema: type[T], overrides: Mapping[str, Any] | None) -> T | str:
    """Return the validated model, or a short error string to show the model in the repair prompt."""
    if not response.content:
        return "the reply had no text content"
    try:
        data = json.loads(extract_json(response.content))
    except json.JSONDecodeError as e:
        return f"body: Invalid JSON: {e.msg}"
    if not isinstance(data, dict):
        return "body: expected a JSON object"
    try:
        return schema.model_validate({**data, **(overrides or {})})
    except ValidationError as e:
        return "; ".join(_describe_error(err) for err in e.errors()[:5])


def _describe_error(err: Mapping[str, Any]) -> str:
    """"At most 300 characters" alone did not get a model under the limit; the actual length does."""
    where = ".".join(map(str, err["loc"])) or "body"
    if err.get("type") == "string_too_long" and isinstance(err.get("input"), str):
        return f"{where}: is {len(err['input'])} characters; the limit is {err.get('ctx', {}).get('max_length')}"
    return f"{where}: {err['msg']}"


class OpenRouterLLM(LLM):
    def __init__(
        self,
        models: list[str] | None = None,
        api_key: str | None = None,
        *,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        max_tries: int = MAX_TRIES_PER_MODEL,
        timeout_s: float = TIMEOUT_S,
        temperature: float | None = None,
    ) -> None:
        self.models = models_from_env({MODELS_ENV: ",".join(models)}) if models is not None else models_from_env()
        self._key = api_key if api_key is not None else os.environ.get(KEY_ENV, "")
        if not self._key:
            raise LLMConfigError(f"{KEY_ENV} is not set")
        if max_tries < 1:
            raise ValueError("max_tries must be at least 1")
        self._transport = transport
        self._sleep = sleep
        self._jitter = jitter
        self.max_tries = max_tries
        self.timeout_s = timeout_s
        # Left out of the request unless set, so every existing caller keeps each model's own default. The
        # calibration script sets 0 to make a critic's scores repeatable; a model that rejects the field answers 400
        # and the chain moves to the next one like any other skip.
        self.temperature = temperature
        # Models that answered 404 on this client. A run makes many chat() calls (tool rounds, repair, revisions),
        # and a retired model at the head of the chain cost one budget slot on every one of them (run_..._c48e24).
        self._dead: set[str] = set()

    def __repr__(self) -> str:
        return f"OpenRouterLLM(models={self.models!r})"  # never the key

    def backoff_s(self, attempt: int) -> float:
        """Exponential with full-range jitter, so parallel runs hitting one shared pool do not retry in lockstep."""
        return min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** (attempt - 1)) * (0.5 + self._jitter())

    def chat(self, run_id: str, agent: Agent, messages: list[Message],
             tools: list[dict[str, Any]] | None = None, *, max_tokens: int = DEFAULT_MAX_TOKENS,
             budget: Budget | None = None) -> LLMResponse:
        summary_in = json.dumps({"messages": messages, "tools": [t["function"]["name"] for t in tools or []]},
                                ensure_ascii=False)
        for index, model in enumerate(self.models):
            if model in self._dead:
                continue
            for attempt in range(1, self.max_tries + 1):
                if budget is not None and not budget.take():
                    blocker = budget.exhausted_by() or budget
                    trace.log_event(run_id, agent, "decision", f"{model}: attempt budget",
                                    f"stop: upstream attempt budget of {blocker.limit} used up", ok=False,
                                    model=model)
                    raise _budget_error(agent, budget)
                outcome = self._attempt(model, messages, tools, max_tokens)
                if isinstance(outcome, LLMResponse):
                    trace.log_event(run_id, agent, "llm_call", summary_in, _describe(outcome), ok=True,
                                    model=outcome.model, latency_ms=outcome.latency_ms)
                    return outcome
                failure, latency_ms = outcome
                trace.log_event(run_id, agent, "llm_call", summary_in,
                                f"attempt {attempt}/{self.max_tries} failed: {failure.reason}", ok=False,
                                model=model, latency_ms=latency_ms)
                if failure.kind == "fatal":
                    trace.log_event(run_id, agent, "decision", f"{model}: {failure.reason}",
                                    "stop: auth or billing error, no fallback", ok=False, model=model)
                    raise LLMAuthError(f"{model}: {failure.reason}")
                if failure.kind == "dead":
                    self._dead.add(model)
                    trace.log_event(run_id, agent, "decision", f"{model}: {failure.reason}",
                                    "dead for the rest of this run: skipped on later calls", ok=False, model=model)
                if failure.kind == "transient" and attempt < self.max_tries:
                    delay = self.backoff_s(attempt)
                    trace.log_event(run_id, agent, "decision", f"{model}: {failure.reason}",
                                    f"backoff {delay:.1f}s, then retry {attempt + 1}/{self.max_tries}",
                                    ok=True, model=model)
                    self._sleep(delay)
                    continue
                break
            next_model = next((m for m in self.models[index + 1:] if m not in self._dead), None)
            trace.log_event(run_id, agent, "decision", f"{model} gave up",
                            f"fallback to {next_model}" if next_model else "no models left", ok=False, model=model)
        raise LLMUnavailable(f"all {len(self.models)} models failed")

    def _attempt(self, model: str, messages: list[Message], tools: list[dict[str, Any]] | None,
                 max_tokens: int) -> LLMResponse | tuple[_Failure, int]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": False}
        if tools:
            payload["tools"] = tools
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
                   "X-Title": "Autopilot"}
        started = time.perf_counter()
        try:
            response = self._transport(OPENROUTER_URL, headers, json.dumps(payload).encode(), self.timeout_s)
        except TimeoutError as e:
            return _Failure("transient", f"timeout: {e}"), _ms(started)
        except OSError as e:
            return _Failure("transient", f"network: {e}"), _ms(started)
        latency_ms = _ms(started)
        if response.status != 200:
            return _Failure(classify_status(response.status), f"HTTP {response.status}: {response.body[:300]}"), latency_ms
        parsed = parse_completion(model, response.body, latency_ms)
        return (parsed, latency_ms) if isinstance(parsed, _Failure) else parsed


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


class MockLLM(LLM):
    """Scripted answers for tests and dry runs: no network, but the same trace events and repair path as the real chain."""

    def __init__(self, script: list[str | LLMResponse | Exception], model: str = "mock/model:free") -> None:
        self._script = list(script)
        self.model = model
        self.calls: list[list[Message]] = []
        self.tools_offered: list[list[str]] = []

    def chat(self, run_id: str, agent: Agent, messages: list[Message],
             tools: list[dict[str, Any]] | None = None, *, max_tokens: int = DEFAULT_MAX_TOKENS,
             budget: Budget | None = None) -> LLMResponse:
        if budget is not None and not budget.take():
            raise _budget_error(agent, budget)
        self.calls.append(list(messages))
        self.tools_offered.append([t["function"]["name"] for t in tools or []])
        if not self._script:
            raise LLMUnavailable("MockLLM script exhausted")
        item = self._script.pop(0)
        summary_in = json.dumps({"messages": messages}, ensure_ascii=False)
        if isinstance(item, Exception):
            trace.log_event(run_id, agent, "llm_call", summary_in, f"failed: {item}", ok=False, model=self.model)
            raise item
        response = item if isinstance(item, LLMResponse) else LLMResponse(model=self.model, content=item)
        trace.log_event(run_id, agent, "llm_call", summary_in, _describe(response), ok=True,
                        model=response.model, latency_ms=response.latency_ms)
        return response
