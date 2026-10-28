"""Build the Hugging Face Space bundle (only the backend's code) and, unless --build-only, upload it.

    python -m scripts.deploy_space --build-only --out build/space
    python -m scripts.deploy_space --space <hf-user>/autopilot-api        # needs HF_TOKEN with write access

The bundle is an allowlist, so data/, .env, the local app's Gradio page and the tests can never be shipped.
Uploading replaces the Space's files, which makes the Space rebuild its image.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from harness import trace

PACKAGES = ("agents", "backend", "harness", "loops", "mcp_server", "scripts")
FILES = ("requirements.txt", "requirements-api.txt", "ui/__init__.py", "ui/controller.py")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "Dockerfile")
TOKEN_ENV = "HF_TOKEN"

# The Space's settings header; app_port must match the Dockerfile.
README = """---
title: Autopilot API
emoji: 🛫
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

The private backend of Autopilot. Built from https://github.com/kkazei/autopilot by scripts/deploy_space.py;
do not edit here.
"""


def build(out: Path, root: Path = trace.REPO_ROOT) -> list[str]:
    """Write the bundle into an empty `out` and return the relative paths it holds."""
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refused: {out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES:
        shutil.copytree(root / package, out / package, ignore=IGNORE)
    for name in FILES:
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, out / name)
    shutil.copy2(root / "backend" / "Dockerfile", out / "Dockerfile")
    (out / "README.md").write_text(README, encoding="utf-8")
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())


def upload(bundle: Path, space: str, token: str) -> str:
    from huggingface_hub import HfApi  # deploy-only dependency, installed by the deploy workflow

    commit = HfApi(token=token).upload_folder(
        repo_id=space, repo_type="space", folder_path=str(bundle),
        commit_message="deploy from github", delete_patterns=["*"])
    return str(commit.commit_url) if hasattr(commit, "commit_url") else str(commit)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="deploy_space", description=__doc__.split("\n")[0])
    p.add_argument("--space", help="the Space id, <user>/<name>")
    p.add_argument("--build-only", action="store_true")
    p.add_argument("--out", type=Path, help="where to build (default: a temporary folder)")
    args = p.parse_args(argv)
    if not args.build_only and not args.space:
        p.error("--space is required unless --build-only")
    with tempfile.TemporaryDirectory(prefix="space-") as tmp:
        out = args.out or Path(tmp) / "space"
        files = build(out)
        print(f"bundle: {len(files)} files in {out}", flush=True)
        if args.build_only:
            return 0
        token = os.environ.get(TOKEN_ENV)
        if not token:
            print(f"refused: {TOKEN_ENV} is not set", flush=True)
            return 2
        print(f"uploaded: {upload(out, args.space, token)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
