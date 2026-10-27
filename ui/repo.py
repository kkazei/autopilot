"""The app's GitHub buttons: how far behind GitHub this copy is, a fast-forward pull, and saving data/ as a PR.

Saving never touches the checkout or the current branch: it builds a commit of data/ on top of origin/master in a
throwaway index and pushes it to a new data/... branch, so the person still merges every data PR themselves and
master is never pushed to from here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from harness import trace

REMOTE, BASE = "origin", "master"
UPSTREAM = f"{REMOTE}/{BASE}"
DATA = "data/"
NETWORK_TIMEOUT_S = 60.0
LOCAL_TIMEOUT_S = 30.0


class RepoError(RuntimeError):
    """A git or gh step failed or was refused; the message is safe to show (redacted)."""


def _git(*args: str, env: dict[str, str] | None = None, check: bool = True, timeout: float = LOCAL_TIMEOUT_S,
         root: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=root or trace.REPO_ROOT, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RepoError(f"git {args[0]} did not run ({type(e).__name__})") from e
    if check and proc.returncode != 0:
        raise RepoError(trace.redact(f"git {args[0]} failed: {(proc.stderr or proc.stdout).strip()}"))
    return proc


def _fetch(root: Path | None) -> None:
    _git("fetch", "--quiet", REMOTE, BASE, timeout=NETWORK_TIMEOUT_S, root=root)


def _branch(root: Path | None) -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD", root=root).stdout.strip()


def _behind(root: Path | None) -> int:
    return int(_git("rev-list", "--count", f"HEAD..{UPSTREAM}", root=root).stdout.strip())


def _local_changes(root: Path | None, pathspec: str = DATA) -> dict[str, str]:
    """{path: two-letter porcelain code} for everything uncommitted under `pathspec`, untracked files included."""
    out = _git("status", "--porcelain", "-z", "--untracked-files=all", "--", pathspec, root=root).stdout
    return {entry[3:]: entry[:2] for entry in out.split("\0") if entry}


def status(root: Path | None = None) -> str:
    """Reads only (a fetch updates origin/master, nothing else), so it is safe to run at any time."""
    _fetch(root)
    branch, behind = _branch(root), _behind(root)
    changed = len(_local_changes(root))
    lines = [f"On branch `{branch}`."]
    lines.append(f"**Behind GitHub by {behind} commit(s).** Pull before saving." if behind
                 else "Up to date with GitHub.")
    lines.append(f"{changed} file(s) under data/ are not on GitHub yet." if changed
                 else "Nothing under data/ waiting to be saved.")
    return "\n\n".join(lines)


def pull(root: Path | None = None) -> str:
    """Fast-forward only, on master only. Local data/ files that GitHub already has byte for byte (what a merged
    Save PR leaves behind) are cleared first, because git refuses to overwrite them even when they are identical."""
    branch = _branch(root)
    if branch != BASE:
        raise RepoError(f"Pull only runs on {BASE}; this copy is on `{branch}`.")
    _fetch(root)
    behind = _behind(root)
    if not behind:
        return "Already up to date."
    incoming = set(_git("diff", "--name-only", "HEAD", UPSTREAM, "--", DATA, root=root).stdout.split("\n")) - {""}
    local = {p: code for p, code in _local_changes(root).items() if p in incoming}
    differ = [p for p in local if not _same_as_upstream(p, root)]
    if differ:
        raise RepoError("Not pulled: these data files differ between this copy and GitHub, so a person has to "
                        "decide which to keep: " + ", ".join(sorted(differ)))
    for path, code in local.items():
        if code == "??":
            (root or trace.REPO_ROOT).joinpath(path).unlink()
        else:
            _git("checkout", "HEAD", "--", path, root=root)
    _git("merge", "--ff-only", "--quiet", UPSTREAM, root=root)
    cleared = f" ({len(local)} local copies already matched GitHub)" if local else ""
    return f"Pulled {behind} commit(s){cleared}."


def _same_as_upstream(path: str, root: Path | None) -> bool:
    """git's own hash, so line-ending conversion counts the same way it would in a commit."""
    full = (root or trace.REPO_ROOT) / path
    if not full.is_file():
        return False
    theirs = _git("rev-parse", "--verify", "--quiet", f"{UPSTREAM}:{path}", check=False, root=root).stdout.strip()
    return bool(theirs) and _git("hash-object", "--", path, root=root).stdout.strip() == theirs


def save_data_pr(now: datetime, root: Path | None = None, gh: Sequence[str] | None = None) -> str:
    """Commit data/ as it is on disk onto origin/master, push it to a new branch and open a PR. Returns the PR URL.
    `gh` is the command that runs the GitHub CLI; tests pass a stand-in."""
    if gh is None:
        found = shutil.which("gh")
        if found is None:
            raise RepoError("The GitHub CLI (gh) is not installed or not on PATH.")
        gh = [found]
    _fetch(root)
    if _git("merge-base", "--is-ancestor", UPSTREAM, "HEAD", check=False, root=root).returncode != 0:
        raise RepoError("This copy is behind GitHub. Pull first, so the PR cannot undo newer data.")
    with tempfile.TemporaryDirectory(prefix="autopilot-save-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git("read-tree", UPSTREAM, env=env, root=root)
        _git("add", "--all", "--", DATA, env=env, root=root)
        changed = _git("diff", "--cached", "--name-status", UPSTREAM, env=env, root=root).stdout.strip()
        if not changed:
            return "Nothing new under data/ to save."
        _refuse_secrets([line.split("\t")[-1] for line in changed.splitlines()], root)
        tree = _git("write-tree", env=env, root=root).stdout.strip()
    title = f"data: local runs saved from the app, {now:%b %d %H:%M} UTC"
    commit = _git("commit-tree", tree, "-p", UPSTREAM, "-m", title, root=root).stdout.strip()
    branch = f"data/app-{now:%Y%m%d-%H%M%S}"
    _git("push", "--quiet", REMOTE, f"{commit}:refs/heads/{branch}", timeout=NETWORK_TIMEOUT_S, root=root)
    listed = changed.splitlines()
    more = f"\n... and {len(listed) - 100} more" if len(listed) > 100 else ""
    body = ("Saved from the local app. Only files under data/ are included; nothing here touches code.\n\n"
            "```\n" + "\n".join(listed[:100]) + more + "\n```")
    try:
        proc = subprocess.run([*gh, "pr", "create", "--base", BASE, "--head", branch, "--title", title, "--body", body],
                              cwd=root or trace.REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=NETWORK_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RepoError(f"Pushed branch {branch}, but gh did not run ({type(e).__name__}). Open the PR on GitHub.") from e
    if proc.returncode != 0:
        raise RepoError(trace.redact(f"Pushed branch {branch}, but the PR was not opened: {proc.stderr.strip()}"))
    return proc.stdout.strip().splitlines()[-1]


def _refuse_secrets(paths: list[str], root: Path | None) -> None:
    """The traces are redacted when written; this checks again, because a PR is public the moment it is pushed."""
    base = root or trace.REPO_ROOT
    for path in paths:
        full = base / path
        if full.is_file():
            text = full.read_bytes().decode("utf-8", errors="replace")
            if trace.redact(text) != text:
                raise RepoError(f"Not saved: {path} looks like it contains a secret. Nothing was pushed.")
