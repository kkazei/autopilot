"""Run one Hermes invocation for one role, inside a throwaway HERMES_HOME, behind the harness's LLM proxy.

Everything Hermes needs is built here and deleted afterwards: a config that points at the proxy (never at
OpenRouter), a role prompt in SOUL.md, and an MCP server started with AUTOPILOT_ROLE so the role's allowlist
is enforced by the server itself. Hermes gets no API key; the child's environment is scrubbed of anything
that looks like a secret so it cannot pick a different provider (or a paid one) on its own.

Never `hermes -z`: that path builds the agent without an iteration limit (one test made 610 tool calls in
two minutes). `chat --oneshot` honours --max-turns, and the proxy's request cap is the second fence.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.trace import REPO_ROOT

SERVER_KEY = "autopilot"
TOOL_PREFIX = f"mcp__{SERVER_KEY}__"
HERMES_ENV = "AUTOPILOT_HERMES_BIN"
DEFAULT_TIMEOUT_S = 180.0
KILL_WAIT_S = 5.0  # how long to wait for the pipes after a kill before giving up on them
DEFAULT_MAX_TURNS = 6
MIN_CONTEXT = 65536
# Provider keys come in many shapes (OPENAI_API_KEY, AWS_ACCESS_KEY_ID, FOO_KEY). A bare "KEY" would also strip
# GIT_CONFIG_KEY_0, which git needs to keep paired with its value.
_PROXY_VAR = re.compile(r"^(HTTP|HTTPS|ALL|FTP)_PROXY$", re.I)
_LOOPBACK = "127.0.0.1,localhost,::1"
_SECRETISH = re.compile(r"API_KEY|ACCESS_KEY|_KEY$|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.I)


class HermesRunError(RuntimeError):
    """A Hermes run that cannot be trusted. `code` names why, so the trace and the tests can tell causes apart."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class HermesResult:
    exit_code: int
    final_text: str | None  # None when the stream never reached its closing `result` event
    stdout: str
    stderr: str
    events: tuple[dict[str, Any], ...] = ()
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class HermesSpec:
    """What one invocation needs. The proxy token is the only credential, and it is only good for one run."""

    role: str
    system_prompt: str
    user_prompt: str
    base_url: str
    proxy_token: str
    tools: tuple[str, ...]
    data_dir: Path
    call_log: Path
    model_label: str = "autopilot/proxy"
    max_turns: int = DEFAULT_MAX_TURNS
    timeout_s: float = DEFAULT_TIMEOUT_S
    extra_env: dict[str, str] = field(default_factory=dict)


def find_hermes() -> str:
    exe = os.environ.get(HERMES_ENV) or shutil.which("hermes")
    if not exe:
        raise HermesRunError("hermes_missing", f"no hermes on PATH (or set {HERMES_ENV})")
    return exe


def build_config(spec: HermesSpec) -> dict[str, Any]:
    """JSON is valid YAML, so this needs no PyYAML. Every key here was verified against the pinned Hermes
    (handoff section 9): turn off whatever would make an extra LLM call, call the network or remember things."""
    server_env = {"AUTOPILOT_ROLE": spec.role, "AUTOPILOT_DATA_DIR": str(spec.data_dir),
                  "AUTOPILOT_TOOL_LOG": str(spec.call_log), "PYTHONIOENCODING": "utf-8"}
    return {
        "model": {"provider": "custom", "default": spec.model_label, "base_url": spec.base_url,
                  "api_key": spec.proxy_token, "context_length": MIN_CONTEXT, "streaming": False},
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        "tools": {"tool_search": {"enabled": "off"}},
        "auxiliary": {"title_generation": {"enabled": False}},
        "updates": {"check": False},
        "agent": {"api_max_retries": 1, "auto_recovery_cycles": 0},
        "mcp_servers": {SERVER_KEY: {
            "command": sys.executable, "args": ["-m", "mcp_server.server"], "env": server_env,
            "cwd": str(REPO_ROOT), "timeout": 60, "connect_timeout": 60,
            "tools": {"include": list(spec.tools), "prompts": False, "resources": False}}},
    }


def child_env(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """No inherited secrets: a stray OPENROUTER_API_KEY would let Hermes bypass the proxy."""
    env = {k: v for k, v in os.environ.items() if not _SECRETISH.search(k) and not _PROXY_VAR.match(k)}
    # A proxy variable would send Hermes's requests to the harness proxy (and its bearer token) through someone else's.
    env.update({"HERMES_HOME": str(home), "PYTHONIOENCODING": "utf-8", "NO_PROXY": _LOOPBACK, "no_proxy": _LOOPBACK})
    env.update(extra or {})
    return env


def build_command(spec: HermesSpec, query_file: Path) -> list[str]:
    # --query-file, not -q: the prompt holds the brief and a draft, and the command line is a poor place for them.
    return [find_hermes(), "chat", "--query-file", str(query_file), "--oneshot", "-Q", "--format", "stream-json",
            "--provider", "custom", "-m", spec.model_label, "-t", SERVER_KEY, "--max-turns", str(spec.max_turns)]


def kill_tree(proc: subprocess.Popen[str]) -> None:
    """Hermes starts the MCP server as a child, and a plain kill would leave it running."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()


def parse_events(stdout: str) -> tuple[dict[str, Any], ...]:
    """stream-json is one JSON object per line; anything else on stdout is ignored, not trusted."""
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    return tuple(events)


def run_hermes(spec: HermesSpec, *, keep_dir: Path | None = None) -> HermesResult:
    """One bounded invocation. Raises HermesRunError for a timeout or a missing binary; the caller cross-checks the rest."""
    workdir = Path(tempfile.mkdtemp(prefix=f"autopilot_hermes_{spec.role}_"))
    try:
        home = workdir / "home"
        home.mkdir()
        (home / "config.yaml").write_text(json.dumps(build_config(spec), indent=2), encoding="utf-8")
        (home / "SOUL.md").write_text(spec.system_prompt, encoding="utf-8")
        query = workdir / "query.txt"
        query.write_text(spec.user_prompt, encoding="utf-8")
        kwargs: dict[str, Any] = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                                  else {"start_new_session": True})
        started = time.monotonic()
        try:
            proc = subprocess.Popen(build_command(spec, query), cwd=home, env=child_env(home, spec.extra_env),
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace", **kwargs)
        except OSError as e:  # not executable, a bad shim, access denied: the caller falls back like for a timeout
            raise HermesRunError("launch_failed", type(e).__name__) from None
        try:
            stdout, stderr = proc.communicate(timeout=spec.timeout_s)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            try:
                proc.communicate(timeout=KILL_WAIT_S)
            except subprocess.TimeoutExpired:
                pass  # a straggler outside the killed tree still holds a pipe; do not wait for it forever
            raise HermesRunError("timeout", f"no answer within {spec.timeout_s:.0f}s; process tree killed") from None
        events = parse_events(stdout)
        return HermesResult(proc.returncode, _final_text(events), stdout, stderr, events,
                            time.monotonic() - started)
    finally:
        if keep_dir is not None and workdir.exists():
            shutil.copytree(workdir, keep_dir, dirs_exist_ok=True)
        shutil.rmtree(workdir, ignore_errors=True)


def _final_text(events: tuple[dict[str, Any], ...]) -> str | None:
    """The `result` event closes a stream (seen against Hermes 0.21.4: system, tool_use, tool_result, result).
    Without it the run was cut short, and stdout is not a reply we can trust."""
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    text = result.get("text") if result else None
    return text if isinstance(text, str) else None
