"""backend/Dockerfile and render.yaml: the image copies only backend code, and no secret value lives in the repo."""

from __future__ import annotations

import re
from pathlib import Path

from backend import app as backend
from harness import llm

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
BLUEPRINT = (ROOT / "render.yaml").read_text(encoding="utf-8")


def copied_sources() -> list[str]:
    sources: list[str] = []
    for line in DOCKERFILE.splitlines():
        if line.startswith("COPY "):
            parts = [p for p in line.split()[1:] if not p.startswith("--")]
            sources += parts[:-1]
    return sources


def test_the_image_copies_named_backend_paths_only():
    sources = copied_sources()
    assert "." not in sources and "./" not in sources  # no copy-everything, which would ship data/ and .env
    assert not [s for s in sources if s.startswith(("data", "tests", "web", "vendor", ".env")) or s == "ui/app.py"]
    for s in sources:
        assert (ROOT / s).exists(), f"Dockerfile copies {s}, which does not exist"


def test_the_blueprint_declares_every_secret_without_a_value():
    keys = re.findall(r"- key: (\S+)\n\s+sync: false", BLUEPRINT)
    assert set(keys) == {llm.KEY_ENV, "OPENROUTER_MODELS", "BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD",
                         "DATABASE_URL", backend.SECRET_ENV}
    assert "value:" not in BLUEPRINT
    assert "plan: free" in BLUEPRINT and "dockerfilePath: ./backend/Dockerfile" in BLUEPRINT
