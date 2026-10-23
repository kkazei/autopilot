"""Tests for the D1-S stub MCP server. No network: the stdio test spawns the server locally."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_server import stub_server

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULT_RE = re.compile(r"^echo_brand OK: (?P<name>.+) \[receipt=(?P<receipt>[0-9a-f]{16})\]$")


def read_log(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def call_log(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "calls.jsonl"
    monkeypatch.setenv(stub_server.CALL_LOG_ENV, str(path))
    return path


def test_echo_brand_returns_name_and_receipt(call_log):
    match = RESULT_RE.match(stub_server.echo_brand("Juniper & Oak"))
    assert match and match["name"] == "Juniper & Oak"


def test_echo_brand_records_matching_call(call_log):
    result = stub_server.echo_brand("Acme")
    [entry] = read_log(call_log)
    assert entry["tool"] == "echo_brand" and entry["name"] == "Acme"
    assert f"receipt={entry['receipt']}" in result


def test_receipts_are_unique_per_call(call_log):
    stub_server.echo_brand("Acme")
    stub_server.echo_brand("Acme")
    receipts = [e["receipt"] for e in read_log(call_log)]
    assert len(set(receipts)) == 2


async def _call_over_stdio(call_log: Path) -> tuple[list[str], str]:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(REPO_ROOT / "mcp_server" / "stub_server.py")],
        env={stub_server.CALL_LOG_ENV: str(call_log)},
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            result = await session.call_tool("echo_brand", {"name": "StdioBrand"})
            return tools, result.content[0].text


def test_server_exposes_only_echo_brand_over_stdio(call_log):
    tools, text = asyncio.run(_call_over_stdio(call_log))
    assert tools == ["echo_brand"]
    match = RESULT_RE.match(text)
    assert match and match["name"] == "StdioBrand"
    [entry] = read_log(call_log)
    assert entry["receipt"] == match["receipt"]
