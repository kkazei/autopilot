"""MCP server tests (D1-A): per-role tool allowlists, harness-only tools, dry run, call log.

Uses DRY_RUN and temp data dirs only. The stdio tests spawn the real server locally.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from harness.trace import DATA_DIR_ENV
from mcp_server import bluesky, server

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t" * 32
LEARNING = {"run_id": "run_1", "post_id": "p1", "metrics": {"likes": 2, "reposts": 0, "replies": 1},
            "insight": "Posts about crust sound got replies."}


@pytest.fixture
def env(tmp_path, monkeypatch) -> Path:
    """A temp data dir with the real brief, harness role and DRY_RUN; tests override per case."""
    shutil.copy(REPO_ROOT / "data" / "brand_brief.json", tmp_path / "brand_brief.json")
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(server.CALL_LOG_ENV, str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv(server.ROLE_ENV, "harness")
    monkeypatch.setenv(server.TOKEN_ENV, TOKEN)
    monkeypatch.setenv(server.DRY_RUN_ENV, "1")
    return tmp_path


def call_log(data: Path) -> list[dict]:
    return [json.loads(line) for line in (data / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


# ---------- tools, called in-process ----------

def test_get_brand_brief_returns_brief(env):
    assert server.get_brand_brief()["name"] == "Bramblewick Bakehouse"


def test_get_brand_brief_rejects_invalid_brief(env):
    (env / "brand_brief.json").write_text('{"name": "x"}', encoding="utf-8")
    with pytest.raises(server.ToolRefused, match="invalid"):
        server.get_brand_brief()


def test_publish_dry_run_returns_fake_uri_without_network(env, monkeypatch):
    monkeypatch.setattr(bluesky, "post", lambda text: pytest.fail("network client called in dry run"))
    result = server.publish_post("Warm bread at 7.", "p1")
    assert result["uri"].startswith("dryrun://p1/") and result["cid"] and result["posted_at"]


def test_publish_accepts_300_and_rejects_301_chars(env):
    assert server.publish_post("x" * 300, "p1")["uri"]
    with pytest.raises(server.ToolRefused, match="301 characters"):
        server.publish_post("x" * 301, "p1")


@pytest.mark.parametrize("post_id", ["", "../x", "a b"])
def test_publish_rejects_bad_post_id(env, post_id):
    with pytest.raises(server.ToolRefused):
        server.publish_post("hi", post_id)


def test_publish_live_without_credentials_fails_cleanly(env, monkeypatch):
    monkeypatch.delenv(server.DRY_RUN_ENV)
    monkeypatch.delenv(bluesky.HANDLE_ENV, raising=False)
    monkeypatch.delenv(bluesky.PASSWORD_ENV, raising=False)
    monkeypatch.setattr(bluesky, "_client", None)
    with pytest.raises(bluesky.BlueskyAuthError):
        server.publish_post("hi", "p1")


def test_live_publish_logs_pending_record_before_calling_bluesky(env, monkeypatch):
    """Audit finding 12: if the post goes out and anything fails after, the log must already show the attempt."""
    monkeypatch.delenv(server.DRY_RUN_ENV)

    def fake_post(text):
        [pending] = call_log(env)
        assert pending["tool"] == "publish_post" and pending["phase"] == "pending" and "hi" in pending["args"]
        return {"uri": "at://did:plc:x/app.bsky.feed.post/1", "cid": "c1"}

    monkeypatch.setattr(bluesky, "post", fake_post)
    assert server.publish_post("hi", "p1")["uri"].startswith("at://")
    pending, final = call_log(env)
    assert final["ok"] is True and "phase" not in final
    assert pending["receipt"] == final["receipt"] and pending["receipt"]


def test_failed_live_publish_keeps_pending_record(env, monkeypatch):
    monkeypatch.delenv(server.DRY_RUN_ENV)

    def boom(text):
        raise bluesky.BlueskyError("connection dropped after send")

    monkeypatch.setattr(bluesky, "post", boom)
    with pytest.raises(bluesky.BlueskyError):
        server.publish_post("hi", "p1")
    pending, final = call_log(env)
    assert pending["phase"] == "pending" and final["ok"] is False and "connection dropped" in final["result"]


@pytest.mark.parametrize("role, token", [("writer", ""), ("harness", "short")])
def test_harness_only_tools_refuse_in_process_without_harness_role(env, monkeypatch, role, token):
    monkeypatch.setenv(server.ROLE_ENV, role)
    monkeypatch.setenv(server.TOKEN_ENV, token)
    with pytest.raises(server.ToolRefused, match="harness-only"):
        server.publish_post("hi", "p1")
    with pytest.raises(server.ToolRefused, match="harness-only"):
        server.save_learning(LEARNING)


def test_get_metrics_dry_run_uri_returns_zeros(env):
    metrics = server.get_metrics("dryrun://p1/abc")
    assert {k: metrics[k] for k in ("likes", "reposts", "replies")} == {"likes": 0, "reposts": 0, "replies": 0}
    assert metrics["fetched_at"]


def test_get_metrics_uses_client_for_real_uris(env, monkeypatch):
    monkeypatch.setattr(bluesky, "get_post_metrics", lambda uri: {"likes": 3, "reposts": 1, "replies": 2})
    assert server.get_metrics("at://did:plc:x/app.bsky.feed.post/1")["likes"] == 3


def test_get_metrics_rejects_unknown_uri_scheme(env):
    with pytest.raises(server.ToolRefused):
        server.get_metrics("https://example.com")


def test_save_and_get_learnings_round_trip(env):
    for i in range(3):
        server.save_learning({**LEARNING, "post_id": f"p{i}"})
    assert [r["post_id"] for r in server.get_learnings(limit=2)] == ["p1", "p2"]


def test_save_learning_rejects_invalid(env):
    with pytest.raises(server.ToolRefused, match="invalid"):
        server.save_learning({"run_id": "r"})
    assert not (env / "learnings.jsonl").exists()


def test_get_learnings_skips_corrupt_lines(env):
    server.save_learning(LEARNING)
    with (env / "learnings.jsonl").open("a", encoding="utf-8") as f:
        f.write("{broken\n" + json.dumps({"run_id": "r"}) + "\n")
    assert len(server.get_learnings()) == 1


@pytest.mark.parametrize("limit", [0, 51])
def test_get_learnings_limit_is_bounded(env, limit):
    with pytest.raises(server.ToolRefused):
        server.get_learnings(limit=limit)


def test_every_call_is_logged_with_unique_receipt(env):
    server.get_brand_brief()
    with pytest.raises(server.ToolRefused):
        server.publish_post("x" * 301, "p1")
    first, second = call_log(env)
    assert first["tool"] == "get_brand_brief" and first["ok"] is True
    assert second["tool"] == "publish_post" and second["ok"] is False and "301" in second["result"]
    assert first["receipt"] != second["receipt"]


def test_call_log_never_contains_the_token(env):
    server.publish_post("hi", "p1")
    assert TOKEN not in (env / "calls.jsonl").read_text(encoding="utf-8")


# ---------- role resolution ----------

@pytest.mark.parametrize("role_env, error", [
    ({}, ValueError),
    ({"AUTOPILOT_ROLE": "admin"}, ValueError),
    ({"AUTOPILOT_ROLE": "harness"}, PermissionError),
    ({"AUTOPILOT_ROLE": "harness", "AUTOPILOT_PUBLISH_TOKEN": "short"}, PermissionError),
    ({"AUTOPILOT_ROLE": "writer", "AUTOPILOT_PUBLISH_TOKEN": TOKEN}, PermissionError),
])
def test_server_refuses_bad_role_config(role_env, error):
    with pytest.raises(error):
        server.build_server(role_env)


def test_harness_only_tools_are_only_in_harness_role():
    for role, tools in server.ROLE_TOOLS.items():
        if role != "harness":
            assert not server.HARNESS_ONLY & set(tools), role
    assert server.HARNESS_ONLY <= set(server.ROLE_TOOLS["harness"])


# ---------- over stdio, as Hermes sees it ----------

async def _session(env: dict[str, str], action) -> object:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_server.server"], env=env, cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await action(session)


async def _list_tools(session: ClientSession) -> list[str]:
    return sorted(t.name for t in (await session.list_tools()).tools)


def stdio_env(data: Path, role: str, **extra: str) -> dict[str, str]:
    return {DATA_DIR_ENV: str(data), server.CALL_LOG_ENV: str(data / "calls.jsonl"),
            server.ROLE_ENV: role, **extra}


@pytest.mark.parametrize("role", ["planner", "writer", "critic", "analyst"])
def test_each_agent_role_sees_only_its_allowlist(env, role):
    tools = asyncio.run(_session(stdio_env(env, role), _list_tools))
    assert tools == sorted(server.ROLE_TOOLS[role])


def test_harness_role_publishes_dry_run_over_stdio(env):
    async def publish(session: ClientSession):
        return await session.call_tool("publish_post", {"text": "Warm bread at 7.", "post_id": "p1"})

    result = asyncio.run(_session(stdio_env(env, "harness", AUTOPILOT_PUBLISH_TOKEN=TOKEN, DRY_RUN="1"), publish))
    assert not result.is_error
    assert result.structured_content["uri"].startswith("dryrun://p1/")
    [entry] = call_log(env)
    assert entry["tool"] == "publish_post" and entry["role"] == "harness" and entry["ok"]


def test_writer_cannot_call_publish_over_stdio(env):
    async def publish(session: ClientSession):
        return await session.call_tool("publish_post", {"text": "hi", "post_id": "p1"})

    result = asyncio.run(_session(stdio_env(env, "writer"), publish))
    assert result.is_error
    assert not (env / "calls.jsonl").exists()
