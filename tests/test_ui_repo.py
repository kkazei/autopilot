"""ui/repo.py against a throwaway bare remote: Save pushes only data/ to a new branch and never moves the checkout
or master; Pull fast-forwards master only, clearing local copies GitHub already has and refusing ones that differ."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ui import repo
from ui.repo import RepoError

NOW = datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)
FAKE_GH = "import json, sys; open(sys.argv[1], 'w').write(json.dumps(sys.argv[2:])); print('https://github.test/pr/1')"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch) -> tuple[Path, Path, Path]:
    """(bare remote, this copy on master, a second copy that stands in for GitHub-side commits)."""
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "t")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@example.com")
    remote, local, other = tmp_path / "remote.git", tmp_path / "local", tmp_path / "other"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(local)], check=True, capture_output=True)
    (local / "data" / "runs").mkdir(parents=True)
    (local / "data" / "approved.jsonl").write_text('{"post_id": "a"}\n')
    (local / "code.py").write_text("x = 1\n")
    git(local, "add", ".")
    git(local, "commit", "-q", "-m", "init")
    git(local, "push", "-q", "origin", "master")
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True, capture_output=True)
    return remote, local, other


def gh(tmp_path: Path) -> tuple[list[str], Path]:
    script, out = tmp_path / "fake_gh.py", tmp_path / "gh_args.json"
    script.write_text(FAKE_GH)
    return [sys.executable, str(script), str(out)], out


def test_save_pushes_only_data_to_a_new_branch_and_leaves_the_checkout_alone(repos, tmp_path):
    remote, local, _ = repos
    (local / "data" / "runs" / "run_1.json").write_text("[]\n")
    (local / "data" / "approved.jsonl").write_text('{"post_id": "a"}\n{"post_id": "b"}\n')
    (local / "code.py").write_text("x = 2\n")  # a code change must never ride along
    before = git(local, "status", "--porcelain"), git(local, "rev-parse", "HEAD")
    master_before = git(remote, "rev-parse", "master")
    cmd, args_file = gh(tmp_path)

    assert repo.save_data_pr(NOW, root=local, gh=cmd) == "https://github.test/pr/1"

    assert (git(local, "status", "--porcelain"), git(local, "rev-parse", "HEAD")) == before
    assert git(remote, "rev-parse", "master") == master_before
    branch = "data/app-20261027-093000"
    assert git(remote, "show", f"{branch}:data/runs/run_1.json") == "[]"
    assert git(remote, "show", f"{branch}:code.py") == "x = 1"
    assert git(remote, "rev-parse", f"{branch}~1") == master_before
    args = json.loads(args_file.read_text())
    assert args[:6] == ["pr", "create", "--base", "master", "--head", branch]
    assert "data/runs/run_1.json" in args[args.index("--body") + 1]


def test_save_with_nothing_new_pushes_nothing(repos, tmp_path):
    remote, local, _ = repos
    cmd, args_file = gh(tmp_path)
    assert repo.save_data_pr(NOW, root=local, gh=cmd) == "Nothing new under data/ to save."
    assert not args_file.exists() and git(remote, "branch", "--list", "data/*") == ""


def test_save_refuses_when_behind_github(repos, tmp_path):
    remote, local, other = repos
    (other / "data" / "learnings.jsonl").write_text("{}\n")
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "scheduled run")
    git(other, "push", "-q", "origin", "master")
    (local / "data" / "runs" / "run_1.json").write_text("[]\n")
    with pytest.raises(RepoError, match="Pull first"):
        repo.save_data_pr(NOW, root=local, gh=gh(tmp_path)[0])
    assert git(remote, "branch", "--list", "data/*") == ""


def test_save_refuses_a_file_that_looks_like_a_secret(repos, tmp_path):
    remote, local, _ = repos
    (local / "data" / "runs" / "run_1.json").write_text('["sk-or-v1-abcdef0123456789"]\n')
    with pytest.raises(RepoError, match="looks like it contains a secret"):
        repo.save_data_pr(NOW, root=local, gh=gh(tmp_path)[0])
    assert git(remote, "branch", "--list", "data/*") == ""


def merged_save(local: Path, other: Path) -> None:
    """What happens after Save: the same file lands on GitHub's master while this copy still has it untracked."""
    (local / "data" / "runs" / "run_1.json").write_text("[]\n")
    (other / "data" / "runs").mkdir(parents=True, exist_ok=True)
    (other / "data" / "runs" / "run_1.json").write_text("[]\n")
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "data PR merged")
    git(other, "push", "-q", "origin", "master")


def test_pull_clears_copies_github_already_has_then_fast_forwards(repos):
    remote, local, other = repos
    merged_save(local, other)
    assert "1 local copies already matched" in repo.pull(root=local)
    assert git(local, "rev-parse", "HEAD") == git(remote, "rev-parse", "master")
    assert git(local, "status", "--porcelain") == ""
    assert repo.pull(root=local) == "Already up to date."


def test_pull_refuses_when_a_local_data_file_differs_and_changes_nothing(repos):
    _, local, other = repos
    merged_save(local, other)
    (local / "data" / "runs" / "run_1.json").write_text('["mine"]\n')
    head = git(local, "rev-parse", "HEAD")
    with pytest.raises(RepoError, match="data/runs/run_1.json"):
        repo.pull(root=local)
    assert git(local, "rev-parse", "HEAD") == head
    assert (local / "data" / "runs" / "run_1.json").read_text() == '["mine"]\n'


def test_pull_only_runs_on_master(repos):
    _, local, _ = repos
    git(local, "checkout", "-q", "-b", "feat/x")
    with pytest.raises(RepoError, match="only runs on master"):
        repo.pull(root=local)


def test_status_says_how_far_behind_and_what_is_unsaved(repos):
    _, local, other = repos
    merged_save(local, other)
    text = repo.status(root=local)
    assert "Behind GitHub by 1 commit(s)" in text and "1 file(s) under data/" in text
