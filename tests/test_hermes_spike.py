"""Tests for the spike script's safety-critical helpers: redaction and the restricted Hermes config."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import hermes_spike


def test_redactor_hides_known_secret_and_openrouter_key_shapes():
    redact = hermes_spike.Redactor("my-secret-value")
    out = redact("a my-secret-value b sk-or-v1-abcdef1234567890 c")
    assert "my-secret-value" not in out and "sk-or-v1" not in out
    assert out.count("[REDACTED]") == 2


def test_config_restricts_hermes_to_echo_brand_only(tmp_path):
    hermes_spike.write_config(tmp_path, {"provider": "openrouter"}, tmp_path / "calls.jsonl", "x/y:free")
    config = json.loads((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    server = config["mcp_servers"][hermes_spike.SERVER_KEY]
    assert server["tools"] == {"include": ["echo_brand"], "prompts": False, "resources": False}
    assert config["tools"]["tool_search"]["enabled"] == "off"
    assert config["auxiliary"]["title_generation"]["enabled"] is False
    assert config["auxiliary"]["free_only"] is True
    assert config["memory"] == {"memory_enabled": False, "user_profile_enabled": False}
    assert "api_key" not in json.dumps(config)


def test_dumped_api_errors_keeps_only_type_code_provider(tmp_path):
    dump = {"error": {"type": "RateLimitError",
                      "message": "Error code: 429 - {'provider_name': 'Google AI Studio', 'user_id': 'user_x'}"}}
    (tmp_path / "request_dump_a.json").write_text(json.dumps(dump), encoding="utf-8")
    assert hermes_spike.dumped_api_errors(tmp_path) == ["RateLimitError http=429 provider=Google AI Studio"]
