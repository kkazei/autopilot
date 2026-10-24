"""harness/hermes_runner.py: the config, the command and the process handling, against a fake `hermes`.

The fake is a Python script, so these run anywhere (CI has no Hermes). tests/test_hermes_live_mock.py runs the
real binary when it is installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from harness import hermes_runner as hr

SECRET = "sk-or-v1-REALKEY1234567890"


def make_spec(tmp_path: Path, **overrides) -> hr.HermesSpec:
    kwargs = dict(role="writer", system_prompt="You write one post.", user_prompt="Write it.",
                  base_url="http://127.0.0.1:9/v1", proxy_token="run-token-abcdefghijklmnop", tools=("get_brand_brief",),
                  data_dir=tmp_path / "data", call_log=tmp_path / "calls.jsonl", timeout_s=20)
    return hr.HermesSpec(**{**kwargs, **overrides})


def fake_hermes(tmp_path: Path, monkeypatch, body: str) -> None:
    """Replace the command with `python fake.py`; `body` runs as the fake Hermes."""
    script = tmp_path / "fake_hermes.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    monkeypatch.setattr(hr, "build_command", lambda spec, query_file: [sys.executable, str(script), str(query_file)])


def test_config_points_at_the_proxy_and_never_holds_the_real_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    config = hr.build_config(make_spec(tmp_path))
    text = json.dumps(config)
    assert SECRET not in text
    assert config["model"]["base_url"] == "http://127.0.0.1:9/v1" and config["model"]["provider"] == "custom"
    assert config["model"]["api_key"] == "run-token-abcdefghijklmnop" and config["model"]["streaming"] is False


def test_config_turns_off_everything_that_would_call_out_or_remember(tmp_path):
    config = hr.build_config(make_spec(tmp_path))
    assert config["memory"] == {"memory_enabled": False, "user_profile_enabled": False}
    assert config["auxiliary"]["title_generation"]["enabled"] is False
    assert config["updates"] == {"check": False}
    assert config["tools"]["tool_search"]["enabled"] == "off"
    assert config["agent"] == {"api_max_retries": 1, "auto_recovery_cycles": 0}


def test_config_starts_the_role_server_with_only_the_roles_tools(tmp_path):
    server = hr.build_config(make_spec(tmp_path, role="critic", tools=()))["mcp_servers"][hr.SERVER_KEY]
    assert server["env"]["AUTOPILOT_ROLE"] == "critic" and server["tools"]["include"] == []
    assert server["args"] == ["-m", "mcp_server.server"] and "AUTOPILOT_PUBLISH_TOKEN" not in server["env"]
    writer = hr.build_config(make_spec(tmp_path))["mcp_servers"][hr.SERVER_KEY]
    assert writer["env"]["AUTOPILOT_ROLE"] == "writer" and writer["tools"]["include"] == ["get_brand_brief"]


def test_the_command_never_uses_z_and_always_bounds_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(hr, "find_hermes", lambda: "hermes")
    cmd = hr.build_command(make_spec(tmp_path, max_turns=4), tmp_path / "q.txt")
    assert "-z" not in cmd and "--yolo" not in cmd
    assert cmd[cmd.index("--max-turns") + 1] == "4" and "--oneshot" in cmd
    assert cmd[cmd.index("-t") + 1] == hr.SERVER_KEY and cmd[cmd.index("--format") + 1] == "stream-json"
    assert cmd[cmd.index("--query-file") + 1] == str(tmp_path / "q.txt")


def test_a_missing_hermes_is_a_named_error(monkeypatch):
    monkeypatch.delenv(hr.HERMES_ENV, raising=False)
    monkeypatch.setattr(hr.shutil, "which", lambda name: None)
    with pytest.raises(hr.HermesRunError) as e:
        hr.find_hermes()
    assert e.value.code == "hermes_missing"


def test_the_child_environment_has_no_secrets_and_its_own_home(tmp_path, monkeypatch):
    secrets = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "FOO_KEY",
               "BLUESKY_APP_PASSWORD", "AUTOPILOT_PUBLISH_TOKEN", "SOME_SECRET", "GH_TOKEN", "GOOGLE_CREDENTIALS")
    for name in secrets:
        monkeypatch.setenv(name, "value-that-must-not-leak")
    monkeypatch.setenv("KEEP_ME", "fine")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.autocrlf")  # a pairing git needs, not a secret
    env = hr.child_env(tmp_path / "home")
    assert not [name for name in secrets if name in env]
    assert env["HERMES_HOME"] == str(tmp_path / "home") and env["KEEP_ME"] == "fine"
    assert env["GIT_CONFIG_KEY_0"] == "core.autocrlf"


def test_parse_events_ignores_everything_that_is_not_a_json_object():
    out = 'banner\n{"type": "system"}\n[1, 2]\n{broken\n  {"type": "result", "text": "hi"}  \n'
    assert [e["type"] for e in hr.parse_events(out)] == ["system", "result"]


def test_the_final_text_comes_only_from_a_closing_result_event():
    assert hr._final_text(({"type": "result", "text": "done"},)) == "done"
    assert hr._final_text(({"type": "tool_use", "name": "x"},)) is None
    assert hr._final_text(({"type": "result", "text": 5},)) is None


def test_a_run_returns_the_stream_and_deletes_its_home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    fake_hermes(tmp_path, monkeypatch, """
        import json, os, sys
        home = os.environ["HERMES_HOME"]
        info = {"home": home, "config": os.path.exists(home + "/config.yaml"), "soul": open(home + "/SOUL.md").read(),
                "query": open(sys.argv[1]).read(), "secret_in_env": "OPENROUTER_API_KEY" in os.environ,
                "stdin_closed": sys.stdin.read() == ""}
        print(json.dumps({"type": "result", "exit_code": 0, "text": json.dumps(info)}))
    """)
    result = hr.run_hermes(make_spec(tmp_path))
    info = json.loads(result.final_text)
    assert result.exit_code == 0 and info["config"] and info["soul"] == "You write one post."
    assert info["query"] == "Write it." and info["secret_in_env"] is False and info["stdin_closed"] is True
    assert not Path(info["home"]).exists()  # nothing of the run is left on disk


def test_a_nonzero_exit_is_returned_not_raised(tmp_path, monkeypatch):
    fake_hermes(tmp_path, monkeypatch, "import sys; print('boom', file=sys.stderr); sys.exit(3)")
    result = hr.run_hermes(make_spec(tmp_path))
    assert result.exit_code == 3 and result.final_text is None and "boom" in result.stderr


def alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_a_timeout_kills_the_whole_process_tree(tmp_path, monkeypatch):
    child_pid = tmp_path / "child.pid"
    fake_hermes(tmp_path, monkeypatch, f"""
        import subprocess, sys, time
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        open({str(child_pid)!r}, "w").write(str(child.pid))
        time.sleep(60)
    """)
    started = time.monotonic()
    with pytest.raises(hr.HermesRunError) as e:
        hr.run_hermes(make_spec(tmp_path, timeout_s=3))
    assert e.value.code == "timeout" and time.monotonic() - started < 30
    pid = int(child_pid.read_text())
    for _ in range(40):  # the OS needs a moment to reap the killed grandchild
        if not alive(pid):
            break
        time.sleep(0.25)
    assert not alive(pid), "the MCP-server-like grandchild survived the timeout"


def test_keep_dir_preserves_the_workdir_for_debugging(tmp_path, monkeypatch):
    fake_hermes(tmp_path, monkeypatch, 'print(\'{"type": "result", "exit_code": 0, "text": "ok"}\')')
    hr.run_hermes(make_spec(tmp_path), keep_dir=tmp_path / "kept")
    assert (tmp_path / "kept" / "home" / "config.yaml").exists()


def test_a_proxy_in_the_environment_cannot_carry_loopback_traffic_off_the_machine(tmp_path, monkeypatch):
    for name in ("HTTP_PROXY", "https_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://proxy.example:3128")
    env = hr.child_env(tmp_path / "home")
    assert not [k for k in env if k.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")]
    assert "127.0.0.1" in env["NO_PROXY"] and "localhost" in env["NO_PROXY"]


def test_a_straggler_holding_the_pipes_cannot_hang_the_wait_after_a_kill(tmp_path, monkeypatch):
    # The kill is neutered, so the child keeps stdout open past the timeout, like a grandchild that escaped the tree.
    monkeypatch.setattr(hr, "kill_tree", lambda proc: None)
    monkeypatch.setattr(hr, "KILL_WAIT_S", 1.0)
    fake_hermes(tmp_path, monkeypatch, "import time; time.sleep(8)")
    started = time.monotonic()
    with pytest.raises(hr.HermesRunError) as e:
        hr.run_hermes(make_spec(tmp_path, timeout_s=1))
    assert e.value.code == "timeout" and time.monotonic() - started < 6


def test_a_binary_that_cannot_be_launched_is_a_named_error_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(hr, "build_command", lambda spec, query_file: [str(tmp_path / "no_such_hermes.exe")])
    with pytest.raises(hr.HermesRunError) as e:
        hr.run_hermes(make_spec(tmp_path))
    assert e.value.code == "launch_failed"
