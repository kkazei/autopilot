"""scripts/deploy_space.py: the Space bundle is an allowlist, so data and secrets can never be uploaded."""

from __future__ import annotations

import pytest

from scripts import deploy_space


def test_bundle_holds_the_backend_and_never_data_secrets_or_tests(tmp_path):
    files = deploy_space.build(tmp_path / "space")
    assert {"Dockerfile", "README.md", "backend/app.py", "ui/controller.py", "scripts/run_outer.py",
            "requirements.txt", "requirements-api.txt"} <= set(files)
    assert not [f for f in files if f.startswith(("data/", "tests/", ".env", "vendor/", "web/"))]
    assert not [f for f in files if "__pycache__" in f or f.endswith(".env") or f == "ui/app.py"]
    assert "sdk: docker" in (tmp_path / "space" / "README.md").read_text(encoding="utf-8")


def test_build_refuses_a_folder_that_is_not_empty(tmp_path):
    (tmp_path / "old.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="not empty"):
        deploy_space.build(tmp_path)


def test_upload_needs_a_space_and_a_token(monkeypatch, capsys):
    monkeypatch.delenv(deploy_space.TOKEN_ENV, raising=False)
    with pytest.raises(SystemExit):
        deploy_space.main([])
    assert deploy_space.main(["--space", "someone/autopilot-api"]) == 2
    assert "HF_TOKEN is not set" in capsys.readouterr().out
