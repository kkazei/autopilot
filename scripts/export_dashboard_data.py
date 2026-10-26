"""Export the repo's data as one JSON file for the static dashboard in dashboard/.

    python -m scripts.export_dashboard_data            # writes dashboard/data.json and dashboard/data.js

The dashboard is public once deployed, so this script is the only door out of data/ and it is deliberately narrow:
- It reads only files git tracks (what a deploy from the repo would contain), so an untracked scratch trace never
  shows up. The one known sample trace is also excluded by name.
- Every string goes through the trace redactor, then loses raw at:// URIs, DIDs and CIDs (a post is shown as a
  bsky.app link only). A final scan refuses to write the file if a secret or a raw identifier is still in it.
- It never opens .env.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness import trace
from harness.fileio import read_jsonl

SCHEMA_VERSION = 1
EXCLUDED_RUNS = frozenset({"run_20261022_080056_bb7b95.json"})  # P1 sample dry run: no model calls, not evidence
DASHBOARD_DIR = trace.REPO_ROOT / "dashboard"

_AT_URI = re.compile(r"at://did:[a-z]+:[A-Za-z0-9._:%-]+/app\.bsky\.feed\.post/([A-Za-z0-9]+)")
_DID = re.compile(r"did:[a-z]+:[A-Za-z0-9._:%-]+")
_CID = re.compile(r"\bbafy[a-z2-7]{20,}\b")
_NO_SIGNAL = "Not enough data yet"


def scrub(text: str) -> str:
    """Clean one string for publication: secrets out, raw post identifiers hidden."""
    text = _AT_URI.sub("[post link]", trace.redact(text))
    text = _DID.sub("[did]", text)
    return _CID.sub("[cid]", text)


def clean(value: Any) -> Any:
    """Scrub every string in a JSON-like value, keys included."""
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {scrub(str(k)): clean(v) for k, v in value.items()}
    return value


def bsky_link(uri: str | None) -> str | None:
    """The public bsky.app page for a live post. The profile part of the URL is the account's DID (the app needs one);
    it is a link target only and is never shown as text. Dry-run URIs and anything unexpected give None."""
    m = re.fullmatch(r"at://(did:[a-z]+:[A-Za-z0-9._:%-]+)/app\.bsky\.feed\.post/([A-Za-z0-9]+)", uri or "")
    return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}" if m else None


def tracked_files(repo: Path, data_dir: Path) -> set[Path] | None:
    """Files git tracks under data_dir, or None when that can't be asked (outside the repo, no git).

    None means "no filter"; the caller says so out loud, because the filter is what keeps untracked files private.
    """
    try:
        data_dir.resolve().relative_to(repo.resolve())
    except ValueError:
        return None
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--", str(data_dir)],
                             capture_output=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return {(repo / name).resolve() for name in out.decode("utf-8").split("\0") if name}


def _allowed(path: Path, tracked: set[Path] | None) -> bool:
    return path.name not in EXCLUDED_RUNS and (tracked is None or path.resolve() in tracked)


def _read_posts(data_dir: Path, tracked: set[Path] | None) -> list[dict]:
    """One entry per post: approved.jsonl holds a pending row, then a published or failed row, merged by post."""
    path = data_dir / "approved.jsonl"
    rows = read_jsonl(path)[0] if _allowed(path, tracked) else []
    merged: dict[tuple, dict] = {}
    for row in rows:
        merged.setdefault((row.get("run_id"), row.get("post_id")), {}).update(row)
    posts = []
    for row in merged.values():
        status = row.get("status") or ("published" if row.get("posted_at") else "unknown")
        uri = row.get("uri") or ""
        posts.append({
            "post_id": row.get("post_id"), "run_id": row.get("run_id"), "text": row.get("text", ""),
            "status": status, "dry_run": bool(row.get("dry_run")), "attempt": row.get("attempt"),
            "scores": row.get("scores"), "reasons": row.get("reasons"), "reason": row.get("reason"),
            "when": row.get("posted_at") or row.get("started_at"), "link": bsky_link(uri),
        })
    posts.sort(key=lambda p: p["when"] or "", reverse=True)
    return posts


def _read_learnings(data_dir: Path, tracked: set[Path] | None) -> list[dict]:
    path = data_dir / "learnings.jsonl"
    rows = read_jsonl(path)[0] if _allowed(path, tracked) else []
    out = [{"run_id": r.get("run_id"), "post_id": r.get("post_id"), "metrics": r.get("metrics") or {},
            "insight": r.get("insight", ""), "saved_at": r.get("saved_at"),
            "has_signal": not str(r.get("insight", "")).startswith(_NO_SIGNAL)} for r in rows]
    out.sort(key=lambda r: r["saved_at"] or "", reverse=True)
    # A post can carry an old "not enough data" line and, once likes arrive, a newer learning. Only the newest is
    # shown, so the counts stay one learning per post instead of counting the superseded line.
    seen: set = set()
    return [r for r in out if not (r["post_id"] in seen or seen.add(r["post_id"]))]


def _read_runs(data_dir: Path, tracked: set[Path] | None) -> tuple[list[dict], list[str]]:
    """Return (runs newest first, names of trace files that could not be read)."""
    runs, unreadable = [], []
    for path in sorted((data_dir / "runs").glob("run_*.json")):
        if not _allowed(path, tracked):
            continue
        try:
            events = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(events, list)
        except (OSError, ValueError, AssertionError):
            unreadable.append(path.name)
            continue
        if not events:
            continue
        # The last decision of an outer run is its whole JSON summary: unreadable as a one-line outcome, so skip it.
        decisions = [e for e in events if e.get("kind") == "decision"
                     and not str(e.get("summary_in", "")).startswith("run_summary")]
        runs.append({
            "run_id": path.stem, "started": events[0].get("ts"), "ended": events[-1].get("ts"),
            "label": events[0].get("summary_in", ""), "start": events[0].get("summary_out", ""),
            "final": decisions[-1].get("summary_out", "") if decisions else "",
            "ok": all(e.get("ok", True) for e in events), "llm_calls": sum(e.get("kind") == "llm_call" for e in events),
            "events": [{k: e.get(k) for k in ("ts", "agent", "kind", "summary_in", "summary_out", "ok", "model",
                                              "latency_ms")} for e in events],
        })
    runs.sort(key=lambda r: r["started"] or "", reverse=True)
    return runs, unreadable


def _partial(data_dir: Path) -> list[str]:
    """What is not proven yet, kept short and in line with docs/HANDOFF.md. Hand-maintained: update it with the handoff."""
    items = []
    cal = data_dir / "calibration"
    if (cal / "report.md").exists():
        text = (cal / "report.md").read_text(encoding="utf-8")
        agree, lenient = _agreement(text)
        if agree:
            line = f"Critic calibration is complete: the critic agreed with the hand scores on {agree}"
            line += f" (too lenient on {lenient})" if lenient else ""
            after = cal / "report.after-clarity-anchor.md"
            if after.exists():
                agree2, lenient2 = _agreement(after.read_text(encoding="utf-8"))
                line += f"; after one rubric change, {agree2}" + (f" (too lenient on {lenient2})" if lenient2 else "")
                line += ", a gain within run-to-run noise."
            else:
                line += "; no rubric fix has been measured yet."
            items.append(line)
    else:
        report = next(iter(sorted(cal.glob("report.partial-*.md"))), None)
        m = re.search(r"Drafts: (\d+) in the file, (\d+) scored", report.read_text(encoding="utf-8")) if report else None
        items.append(f"Critic calibration is partial: {m.group(2)} of {m.group(1)} drafts scored." if m
                     else "Critic calibration has not been run.")
    items += [
        "On real drafts the critic passed an invented class time, invented crust details, a claim about customers, "
        "urgency pressure and invented scarcity; human approval caught each one. Its fact and policy checks are not "
        "reliable on the free model.",
        "No organic engagement yet: every learning with signal comes from likes and reposts by people the builder "
        "knows. A real planner citing a learning was shown once, with the planner alone (data/evidence/stage_f).",
        "The scheduled 06:17 UTC run has fired twice (Oct 24 and 25), hours late each time. It only measures.",
        "Failures forced against a real model (data/evidence/stage_d): the rate cap held; prompt injection was resisted "
        "but the run stopped before the critic; the banned phrase and the revision cap were not forced.",
    ]
    return items


def _agreement(report: str) -> tuple[str | None, str | None]:
    """("6 of 10 drafts", "d03, d06") from a calibration report, or None for whatever the report does not state."""
    agree = re.search(r"Agreement: \*\*(\d+) of (\d+)\*\*", report)
    lenient = re.search(r"too lenient\): \d+ \(([^)]*)\)", report)
    return (f"{agree.group(1)} of {agree.group(2)} drafts" if agree else None,
            lenient.group(1) if lenient else None)


def build(data_dir: Path, tracked: set[Path] | None = None, now: datetime | None = None) -> dict:
    """Assemble the whole export. Pure apart from reading files, so tests can point it at a temp folder."""
    posts = _read_posts(data_dir, tracked)
    learnings = _read_learnings(data_dir, tracked)
    runs, unreadable = _read_runs(data_dir, tracked)
    live = [p for p in posts if p["status"] == "published" and not p["dry_run"]]
    # A link's profile part is the DID, which scrub() would hide: links are validated by bsky_link, then attached after.
    links = [p["link"] for p in posts]
    posts = [{**clean({**p, "link": None}), "link": link} for p, link in zip(posts, links)]
    export = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "overview": {
            "live_posts": len(live), "runs": len(runs), "llm_calls": sum(r["llm_calls"] for r in runs),
            "learnings": len(learnings), "learnings_with_signal": sum(l["has_signal"] for l in learnings),
            "partial": _partial(data_dir), "unreadable_traces": unreadable,
        },
        "posts": posts, "learnings": clean(learnings), "runs": clean(runs),
    }
    export["overview"] = clean(export["overview"])
    return export


def check_safe(text: str) -> None:
    """Last gate before anything is written: raise if a secret or a raw identifier survived."""
    if trace.redact(text) != text:
        raise ValueError("export refused: a secret-shaped string survived redaction")
    if _AT_URI.search(text) or re.search(r"\bbafy[a-z2-7]{20,}\b", text) or re.search(r'"did:[a-z]+:', text):
        raise ValueError("export refused: a raw at:// URI, DID or CID survived scrubbing")


def write(export: dict, out_dir: Path) -> list[Path]:
    """Write data.json (canonical) and data.js (the same data as a script, so index.html also works from a file://
    URL, where fetch() is blocked)."""
    text = json.dumps(export, ensure_ascii=False, indent=1)
    check_safe(text)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / "data.json", out_dir / "data.js"]
    paths[0].write_text(text + "\n", encoding="utf-8")
    paths[1].write_text("window.DASHBOARD_DATA = " + text + ";\n", encoding="utf-8")
    return paths


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="export_dashboard_data", description=__doc__.split("\n")[0])
    p.add_argument("--data-dir", type=Path, default=None, help="default: data/ (or AUTOPILOT_DATA_DIR)")
    p.add_argument("--out", type=Path, default=DASHBOARD_DIR)
    args = p.parse_args(argv)
    data_dir = args.data_dir or trace.data_dir()
    tracked = tracked_files(trace.REPO_ROOT, data_dir)
    if tracked is None:
        print("note: not filtering by git (data dir is outside the repo or git failed); only the named sample "
              "trace is excluded", file=sys.stderr)
    export = build(data_dir, tracked)
    paths = write(export, args.out)
    o = export["overview"]
    print(f"exported {o['live_posts']} live posts, {len(export['posts'])} post records, {o['runs']} runs "
          f"({o['llm_calls']} model calls), {o['learnings']} learnings ({o['learnings_with_signal']} with signal)")
    if o["unreadable_traces"]:
        print(f"warning: unreadable traces skipped: {o['unreadable_traces']}", file=sys.stderr)
    for path in paths:
        print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
