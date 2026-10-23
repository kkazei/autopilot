"""Stub MCP server for the D1-S Hermes spike: one tool, echo_brand.

Each call appends a JSONL record (name + a fresh random receipt) to a call log and returns
the receipt in its result. The receipt is generated server-side, so a final model answer
containing it is proof the tool actually ran, not that the model claimed it did.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from mcp.server import MCPServer

CALL_LOG_ENV = "ECHO_BRAND_CALL_LOG"
DEFAULT_CALL_LOG = Path(__file__).resolve().parent.parent / ".hermes_spike" / "echo_brand_calls.jsonl"

server = MCPServer(name="autopilot-stub")


def call_log_path() -> Path:
    """Read per call so tests and the spike can redirect the log without re-importing."""
    return Path(os.environ.get(CALL_LOG_ENV) or DEFAULT_CALL_LOG)


def record_call(name: str, receipt: str) -> None:
    """Append-only JSONL so concurrent or repeated runs never clobber earlier evidence."""
    path = call_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": "echo_brand",
        "name": name,
        "receipt": receipt,
        "pid": os.getpid(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


@server.tool()
def echo_brand(name: str) -> str:
    """Echo a brand name back with a server-generated receipt."""
    receipt = secrets.token_hex(8)
    record_call(name, receipt)
    return f"echo_brand OK: {name} [receipt={receipt}]"


if __name__ == "__main__":
    server.run("stdio")
