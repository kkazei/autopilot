"""D1-S spike: can Hermes Agent call a local MCP tool through a free OpenRouter model?

Two stages, both in an isolated, git-ignored HERMES_HOME so the user's global Hermes config
is never read or changed:

1. gate: Hermes talks to a local mock LLM endpoint on 127.0.0.1 that records every request.
   We assert the tool list Hermes actually sends contains only echo_brand. No external calls.
   If the gate fails, the live stage does not run.
2. live: the same config pointed at OpenRouter with a verified free model. Success needs both
   a server-side call-log record for a random brand name and the server-generated receipt in
   Hermes's final answer, which the model cannot guess.

Standard library only. The API key is read from .env into the child env and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPIKE_ROOT = REPO_ROOT / ".hermes_spike"
STUB_SERVER = REPO_ROOT / "mcp_server" / "stub_server.py"
SERVER_KEY = "autopilot_stub"
# v0.21.4 wire name is mcp__<server>__<tool> (tools/mcp_tool_schema.py); the docs still show single underscores.
EXPECTED_TOOLS = {f"mcp__{SERVER_KEY}__echo_brand"}
OPENROUTER_API = "https://openrouter.ai/api/v1"
DEFAULT_MODELS = [
    "minimax/minimax-m3.1-flash:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
]
MIN_CONTEXT = 65_536
HERMES_TIMEOUT_S = 240
RATE_LIMIT_RE = re.compile(r"\b429\b|rate.?limit", re.IGNORECASE)


# ---------- secrets ----------

def read_env_value(key: str) -> str | None:
    """Environment first, then .env; parsed by hand to avoid a python-dotenv dependency."""
    if os.environ.get(key):
        return os.environ[key]
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == key:
            return value.strip().strip("'\"") or None
    return None


class Redactor:
    """Every line we print passes through here, so a leaked key in Hermes output never reaches the terminal."""

    def __init__(self, *secret_values: str | None) -> None:
        self._secrets = [s for s in secret_values if s]

    def __call__(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "[REDACTED]")
        return re.sub(r"sk-or-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)


# ---------- model metadata ----------

def fetch_json(url: str, api_key: str | None = None, timeout: float = 30) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def verify_models(candidates: list[str]) -> list[dict]:
    """Keep only models whose live metadata says free, tool-capable and >= 64K context."""
    catalog = {m["id"]: m for m in fetch_json(f"{OPENROUTER_API}/models")["data"]}
    verified = []
    for model_id in candidates:
        meta = catalog.get(model_id)
        if meta is None:
            print(f"  model {model_id}: not in OpenRouter catalog, skipped")
            continue
        pricing = meta.get("pricing", {})
        checks = {
            "free_suffix": model_id.endswith(":free"),
            "zero_price": all(float(pricing.get(k, "1") or 0) == 0 for k in ("prompt", "completion")),
            "tools": "tools" in (meta.get("supported_parameters") or []),
            "context>=64K": (meta.get("context_length") or 0) >= MIN_CONTEXT,
        }
        ok = all(checks.values())
        print(f"  model {model_id}: context={meta.get('context_length')} {checks} -> {'OK' if ok else 'REJECTED'}")
        if ok:
            verified.append({"id": model_id, "context_length": meta["context_length"]})
    return verified


# ---------- isolated Hermes home ----------

def write_config(home: Path, model_block: dict, call_log: Path, aux_model: str | None) -> None:
    """JSON is valid YAML, so the config needs no PyYAML. Only the stub server, no memory."""
    config = {
        "model": model_block,
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        # Off, so the model sees the real echo_brand schema, not the generic tool_call dispatcher.
        "tools": {"tool_search": {"enabled": "off"}},
        "mcp_servers": {
            SERVER_KEY: {
                "command": sys.executable,
                "args": [str(STUB_SERVER)],
                "env": {"ECHO_BRAND_CALL_LOG": str(call_log)},
                "cwd": str(REPO_ROOT),
                "timeout": 60,
                "connect_timeout": 60,
                "tools": {"include": ["echo_brand"], "prompts": False, "resources": False},
            }
        },
    }
    # Session titling is an extra LLM call whose "fast" model pick could be a paid SKU: turn it off.
    config["auxiliary"] = {"title_generation": {"enabled": False}}
    if aux_model:
        config["auxiliary"].update({"free_only": True, "openrouter_model": aux_model})
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(json.dumps(config, indent=2), encoding="utf-8")


def run_hermes(home: Path, prompt: str, provider: str, model: str, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    """One-shot run restricted to the stub server's toolset. Never --yolo."""
    hermes = shutil.which("hermes")
    if not hermes:
        raise SystemExit("hermes executable not found on PATH")
    # Minimal env: no inherited provider keys can leak in and pick a different (paid) provider.
    env = {k: v for k, v in os.environ.items() if not re.search(r"API_KEY|TOKEN|SECRET|PASSWORD", k, re.I)}
    env.update({"HERMES_HOME": str(home), "HERMES_DUMP_REQUESTS": "1", "PYTHONIOENCODING": "utf-8"})
    env.update(extra_env)
    cmd = [hermes, "-z", prompt, "--provider", provider, "-m", model, "-t", SERVER_KEY]
    return subprocess.run(
        cmd, cwd=home, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=HERMES_TIMEOUT_S,
    )


def dumped_tool_sets(home: Path) -> list[set[str]]:
    """Tool names from every request body Hermes dumped (HERMES_DUMP_REQUESTS=1)."""
    sets = []
    for dump in sorted(home.rglob("request_dump_*.json")):
        body = json.loads(dump.read_text(encoding="utf-8")).get("request", {}).get("body", {})
        sets.append({t["function"]["name"] for t in body.get("tools") or []})
    return sets


def dumped_api_errors(home: Path) -> list[str]:
    """Hermes records provider failures (429, 404, ...) in error dumps, not in logs/*.log.
    Only type, HTTP code and provider name are kept: the raw body carries account ids."""
    errors = []
    for dump in sorted(home.rglob("request_dump_*.json")):
        error = json.loads(dump.read_text(encoding="utf-8")).get("error")
        if not error:
            continue
        message = str(error.get("message", ""))
        code = re.search(r"Error code: (\d{3})", message)
        provider = re.search(r"'provider_name': '([^']+)'", message)
        errors.append(f"{error.get('type')} http={code[1] if code else '?'} provider={provider[1] if provider else '?'}")
    return errors


def log_lines_matching(home: Path, pattern: re.Pattern) -> list[str]:
    hits = []
    for log in (home / "logs").glob("*.log"):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if pattern.search(line):
                hits.append(f"{log.name}: {line.strip()[:240]}")
    return hits


# ---------- stage 1: local mock gate ----------

class MockLLM(BaseHTTPRequestHandler):
    """OpenAI-compatible stub that records requests and answers with plain text, never a tool call."""

    captured: list[dict] = []

    def log_message(self, *args) -> None:
        pass

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self.captured.append({"method": "GET", "path": self.path})
        self._send(200, b'{"object":"list","data":[]}', "application/json")

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        tools = sorted(t.get("function", {}).get("name", "?") for t in body.get("tools") or [])
        first = next(iter(body.get("messages") or []), {})
        hint = str(first.get("content"))[:70] if isinstance(first, dict) else ""
        self.captured.append({"method": "POST", "path": self.path, "tools": tools, "first_message": hint})
        message = {"role": "assistant", "content": "GATE_OK"}
        if body.get("stream"):
            chunks = [
                {"id": "gate", "object": "chat.completion.chunk", "model": body.get("model"),
                 "choices": [{"index": 0, "delta": message, "finish_reason": None}]},
                {"id": "gate", "object": "chat.completion.chunk", "model": body.get("model"),
                 "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
            ]
            payload = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
            self._send(200, payload.encode(), "text/event-stream")
        else:
            reply = {"id": "gate", "object": "chat.completion", "model": body.get("model"),
                     "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
            self._send(200, json.dumps(reply).encode(), "application/json")


def run_gate(run_dir: Path) -> bool:
    """Fail closed: the live stage only runs if every captured request offers exactly EXPECTED_TOOLS."""
    print("\n== Stage 1: tool-restriction gate (local mock LLM, no external calls)")
    MockLLM.captured = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), MockLLM)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    home = run_dir / "gate_home"
    model_block = {
        "provider": "custom", "default": "mock/gate", "base_url": f"http://127.0.0.1:{httpd.server_port}/v1",
        "api_key": "mock-key-not-a-secret", "context_length": MIN_CONTEXT, "streaming": False,
    }
    write_config(home, model_block, run_dir / "gate_calls.jsonl", aux_model=None)
    try:
        proc = run_hermes(home, "Reply with the single word READY.", "custom", "mock/gate", {})
    finally:
        httpd.shutdown()
    posts = [c for c in MockLLM.captured if c["method"] == "POST"]
    print(f"  hermes rc={proc.returncode} stdout={proc.stdout.strip()[:80]!r}")
    print(f"  mock captured {len(MockLLM.captured)} request(s), {len(posts)} chat POST(s)")
    for c in MockLLM.captured:
        if c["method"] == "GET":
            print(f"    GET  {c['path']}")
        else:
            print(f"    POST {c['path']} tools={c['tools']} first_message={c['first_message']!r}")
    dumps = dumped_tool_sets(home)
    print(f"  request dumps: {[sorted(s) for s in dumps]}")
    ok = bool(posts) and all(set(c["tools"]) == EXPECTED_TOOLS for c in posts) \
        and bool(dumps) and all(s == EXPECTED_TOOLS for s in dumps)
    print(f"  GATE {'PASSED' if ok else 'FAILED'}: expected exactly {sorted(EXPECTED_TOOLS)}")
    if not ok and proc.stderr.strip():
        print("  stderr tail:\n    " + "\n    ".join(proc.stderr.strip().splitlines()[-15:]))
    return ok


# ---------- stage 2: live OpenRouter ----------

def key_usage(api_key: str) -> dict | None:
    """Spend counters for the key, so the report can show the run cost $0."""
    try:
        data = fetch_json(f"{OPENROUTER_API}/key", api_key)["data"]
        return {k: data.get(k) for k in ("usage", "usage_daily", "is_free_tier", "limit_remaining")}
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        return {"error": type(exc).__name__}


def read_calls(call_log: Path) -> list[dict]:
    if not call_log.exists():
        return []
    return [json.loads(line) for line in call_log.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_live_attempt(run_dir: Path, model: dict, api_key: str, redact: Redactor) -> dict:
    home = run_dir / f"live_home_{re.sub(r'[^A-Za-z0-9]+', '_', model['id'])}"
    call_log = run_dir / "live_calls.jsonl"
    brand = f"Brand-{secrets.token_hex(3)}"
    prompt = (
        f"Use the echo_brand tool exactly once with name \"{brand}\". "
        "Then reply with the tool's exact output text and nothing else."
    )
    model_block = {
        "provider": "openrouter", "default": model["id"], "base_url": OPENROUTER_API,
        "context_length": model["context_length"], "streaming": False,
    }
    write_config(home, model_block, call_log, aux_model=model["id"])
    started = time.monotonic()
    try:
        proc = run_hermes(home, prompt, "openrouter", model["id"], {"OPENROUTER_API_KEY": api_key})
        rc, stdout, stderr = proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        rc, stdout, stderr = "timeout", "", f"hermes timed out after {HERMES_TIMEOUT_S}s"
    elapsed = round(time.monotonic() - started, 1)

    calls = [c for c in read_calls(call_log) if c["name"] == brand]
    receipt_in_answer = any(f"receipt={c['receipt']}" in stdout for c in calls)
    dumps = dumped_tool_sets(home)
    return {
        "model": model["id"], "brand": brand, "rc": rc, "elapsed_s": elapsed,
        "final_response": redact(stdout), "stderr_tail": redact("\n".join(stderr.splitlines()[-10:])),
        "server_calls": calls, "receipt_in_answer": receipt_in_answer,
        "request_tool_sets": [sorted(s) for s in dumps],
        "tools_restricted": bool(dumps) and all(s == EXPECTED_TOOLS for s in dumps),
        "api_errors": dumped_api_errors(home),
        "rate_limit_lines": [redact(l) for l in log_lines_matching(home, RATE_LIMIT_RE)][:10],
        "paid_lane_warnings": log_lines_matching(home, re.compile("PAID lane")),
        "success": bool(calls) and receipt_in_answer,
    }


def run_live(run_dir: Path, models: list[dict], api_key: str, redact: Redactor) -> list[dict]:
    print("\n== Stage 2: live run via OpenRouter")
    attempts = []
    for model in models:
        print(f"  trying {model['id']} ...")
        result = run_live_attempt(run_dir, model, api_key, redact)
        attempts.append(result)
        print(f"    rc={result['rc']} elapsed={result['elapsed_s']}s success={result['success']}")
        print(f"    final response: {result['final_response'][:300]!r}")
        print(f"    server-side calls for {result['brand']}: {result['server_calls']}")
        print(f"    receipt in answer: {result['receipt_in_answer']}  tools offered per request: {result['request_tool_sets']}")
        if result["api_errors"]:
            print(f"    provider API errors: {result['api_errors']}")
        if result["rate_limit_lines"]:
            print("    rate-limit evidence:\n      " + "\n      ".join(result["rate_limit_lines"]))
        if result["paid_lane_warnings"]:
            print(f"    WARNING paid-lane log lines: {result['paid_lane_warnings']}")
        if not result["tools_restricted"]:
            print("    STOP: live request offered tools other than echo_brand")
            break
        if result["success"]:
            break
        if result["stderr_tail"]:
            print("    stderr tail:\n      " + "\n      ".join(result["stderr_tail"].splitlines()))
    return attempts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=["gate", "live", "all"], default="all")
    args = parser.parse_args()

    run_dir = SPIKE_ROOT / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    api_key = read_env_value("OPENROUTER_API_KEY")
    redact = Redactor(api_key)
    print(f"run dir: {run_dir}")
    print(f"OPENROUTER_API_KEY present: {bool(api_key)}")
    report: dict = {"run_dir": str(run_dir)}

    if args.stage in ("gate", "all"):
        report["gate_passed"] = run_gate(run_dir)
        if not report["gate_passed"]:
            (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print("\nGate failed: not running the live stage.")
            return 2

    if args.stage in ("live", "all"):
        if not api_key:
            print("OPENROUTER_API_KEY missing: cannot run the live stage.")
            return 3
        candidates = [m.strip() for m in (read_env_value("OPENROUTER_MODELS") or "").split(",") if m.strip()]
        print("\n== Verifying model metadata")
        models = verify_models(candidates or DEFAULT_MODELS)
        if not models:
            print("No verified free tool-capable model available.")
            return 4
        report["key_usage_before"] = key_usage(api_key)
        report["attempts"] = run_live(run_dir, models, api_key, redact)
        report["key_usage_after"] = key_usage(api_key)
        print(f"\n  key usage before: {report['key_usage_before']}")
        print(f"  key usage after:  {report['key_usage_after']}")
        report["success"] = any(a["success"] for a in report["attempts"])
        print(f"\nRESULT: {'SUCCESS - echo_brand executed server-side' if report['success'] else 'FAILED'}")

    (run_dir / "report.json").write_text(redact(json.dumps(report, indent=2)), encoding="utf-8")
    print(f"report: {run_dir / 'report.json'}")
    return 0 if report.get("success", report.get("gate_passed")) else 1


if __name__ == "__main__":
    sys.exit(main())
