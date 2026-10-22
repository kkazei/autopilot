"""Autopilot MCP server: the five tools every role reaches through one process per invocation.

Each process serves one role, fixed at startup by AUTOPILOT_ROLE, and registers only that
role's tools from ROLE_TOOLS. A model therefore cannot even see a tool its role is not
allowed, let alone call it. publish_post and save_learning exist only in a "harness" server,
which also needs AUTOPILOT_PUBLISH_TOKEN. The token guards against misconfiguration (an agent
config accidentally started as harness). It is not authentication: whatever sets the env can
set the token, which is why the harness never passes it to an agent process.

Every call, ok or failed, is appended to a JSONL call log with a server-generated receipt.
The harness ingests that log into the run trace and cross-checks it against Hermes's own
records, so a tool call that Hermes reported but the server never saw (or vice versa) is caught.

Run over stdio from the repo root (Hermes or any MCP client launches it the same way):

    AUTOPILOT_ROLE=writer python -m mcp_server.server
    AUTOPILOT_ROLE=harness AUTOPILOT_PUBLISH_TOKEN=<32+ chars> DRY_RUN=1 python -m mcp_server.server
"""

from __future__ import annotations

import functools
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from pydantic import ValidationError

from harness.fileio import append_jsonl, read_jsonl
from harness.schemas import MAX_POST_CHARS, BrandBrief, Learning
from harness.trace import data_dir, redact
from mcp_server import bluesky

SERVER_NAME = "autopilot"
ROLE_ENV = "AUTOPILOT_ROLE"
TOKEN_ENV = "AUTOPILOT_PUBLISH_TOKEN"
DRY_RUN_ENV = "DRY_RUN"
CALL_LOG_ENV = "AUTOPILOT_TOOL_LOG"
MIN_TOKEN_CHARS = 32
MAX_LEARNINGS = 50
_LOG_FIELD_MAX = 500
POST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    "planner": ("get_brand_brief", "get_learnings"),
    "writer": ("get_brand_brief",),
    "critic": (),
    "analyst": ("get_metrics",),
    "harness": ("get_brand_brief", "publish_post", "get_metrics", "save_learning", "get_learnings"),
}
HARNESS_ONLY = frozenset({"publish_post", "save_learning"})


class ToolRefused(RuntimeError):
    """A clear, model-readable refusal; MCP returns it to the caller as an error result."""


def call_log_path() -> Path:
    return Path(os.environ.get(CALL_LOG_ENV) or data_dir() / "runtime" / "mcp_calls.jsonl")


def _short(value: Any) -> str:
    text = redact(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str))
    return text if len(text) <= _LOG_FIELD_MAX else text[:_LOG_FIELD_MAX] + "...[truncated]"


def _logged(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Record every call with a receipt the model cannot guess, so the harness can prove which calls really ran."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": os.environ.get(ROLE_ENV, ""),
            "tool": fn.__name__,
            "args": _short(kwargs if not args else {"args": args, **kwargs}),
            "receipt": secrets.token_hex(8),
            "pid": os.getpid(),
        }
        started = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            record.update(ok=False, result=_short(f"{type(e).__name__}: {e}"))
            raise
        else:
            record.update(ok=True, result=_short(result))
            return result
        finally:
            record["latency_ms"] = int((time.perf_counter() - started) * 1000)
            append_jsonl(call_log_path(), record)

    return wrapper


def _require_harness() -> None:
    """Second lock on the harness-only tools, for in-process callers that bypass build_server."""
    if os.environ.get(ROLE_ENV) != "harness" or len(os.environ.get(TOKEN_ENV, "")) < MIN_TOKEN_CHARS:
        raise ToolRefused("this tool is harness-only")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@_logged
def get_brand_brief() -> dict[str, Any]:
    """Return the brand brief (name, voice, do/dont lists, banned phrases, goal, CTA link)."""
    path = data_dir() / "brand_brief.json"
    try:
        return BrandBrief.model_validate_json(path.read_text(encoding="utf-8")).model_dump()
    except FileNotFoundError:
        raise ToolRefused("brand brief not found") from None
    except ValidationError as e:
        raise ToolRefused(f"brand brief is invalid: {e.error_count()} errors") from None


@_logged
def publish_post(text: str, post_id: str) -> dict[str, str]:
    """Publish one post. Harness-only; agents never see this tool."""
    _require_harness()
    if not POST_ID_RE.match(post_id):
        raise ToolRefused("post_id must be 1-64 characters of letters, digits, '-' or '_'")
    if not text.strip():
        raise ToolRefused("text is empty")
    if len(text) > MAX_POST_CHARS:
        raise ToolRefused(f"text is {len(text)} characters; Bluesky allows {MAX_POST_CHARS}")
    if os.environ.get(DRY_RUN_ENV) == "1":
        suffix = secrets.token_hex(6)
        return {"uri": f"dryrun://{post_id}/{suffix}", "cid": f"dryrun-{suffix}", "posted_at": _now()}
    posted = bluesky.post(text)
    return {"uri": posted["uri"], "cid": posted["cid"], "posted_at": _now()}


@_logged
def get_metrics(post_uri: str) -> dict[str, Any]:
    """Return likes, reposts and replies for a published post. Dry-run posts always report zeros."""
    if post_uri.startswith("dryrun://"):
        counts = {"likes": 0, "reposts": 0, "replies": 0}
    elif post_uri.startswith("at://"):
        raw = bluesky.get_post_metrics(post_uri)
        counts = {k: int(raw[k]) for k in ("likes", "reposts", "replies")}
    else:
        raise ToolRefused("post_uri must start with at:// or dryrun://")
    return {**counts, "fetched_at": _now()}


@_logged
def save_learning(learning: dict[str, Any]) -> dict[str, Any]:
    """Validate and store one learning. Harness-only; agents never see this tool."""
    _require_harness()
    try:
        validated = Learning.model_validate(learning)
    except ValidationError as e:
        raise ToolRefused(f"learning is invalid: {e.error_count()} errors") from None
    record = {**validated.model_dump(), "saved_at": _now()}
    append_jsonl(data_dir() / "learnings.jsonl", record)
    return record


@_logged
def get_learnings(limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent learnings, newest last. Corrupt lines are skipped, not fatal, so one bad write cannot block planning."""
    if not 1 <= limit <= MAX_LEARNINGS:
        raise ToolRefused(f"limit must be between 1 and {MAX_LEARNINGS}")
    records, _invalid = read_jsonl(data_dir() / "learnings.jsonl")
    valid = []
    for r in records:
        try:
            valid.append({**Learning.model_validate(r).model_dump(), "saved_at": r.get("saved_at")})
        except ValidationError:
            continue
    return valid[-limit:]


TOOLS: dict[str, Callable[..., Any]] = {
    f.__name__: f for f in (get_brand_brief, publish_post, get_metrics, save_learning, get_learnings)
}


def resolve_role(env: Mapping[str, str]) -> str:
    """Fail closed: no role, an unknown role, or a token where it does not belong all refuse to start."""
    role = env.get(ROLE_ENV, "")
    if role not in ROLE_TOOLS:
        raise ValueError(f"{ROLE_ENV} must be one of {sorted(ROLE_TOOLS)}")
    token = env.get(TOKEN_ENV, "")
    if role == "harness" and len(token) < MIN_TOKEN_CHARS:
        raise PermissionError(f"role harness requires {TOKEN_ENV} ({MIN_TOKEN_CHARS}+ chars)")
    if role != "harness" and token:
        raise PermissionError(f"{TOKEN_ENV} must not be passed to an agent role server")
    return role


def build_server(env: Mapping[str, str] | None = None) -> MCPServer:
    role = resolve_role(os.environ if env is None else env)
    server = MCPServer(name=SERVER_NAME)
    for name in ROLE_TOOLS[role]:
        server.add_tool(TOOLS[name])
    return server


def main() -> int:
    try:
        server = build_server()
    except (ValueError, PermissionError) as e:
        print(f"autopilot MCP server refused to start: {e}", file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
