"""The dashboard export is the only door from data/ to a public page, so these tests are mostly about what must NOT get out."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness import trace
from scripts import export_dashboard_data as export

DID = "did:plc:examplefaketestdidonly234"  # made up: not a real account
URI = f"at://{DID}/app.bsky.feed.post/3myhe2q5j432a"
CID = "bafyreic2hwofnqcdosvydkpjgjaqtcpbv6c7b5ifehk3q3msthkmtxk6u4"
API_KEY = "sk-or-v1-0123456789abcdef0123456789abcdef"
APP_PASSWORD = "Zq9!not-a-pattern!Xk2"  # no xxxx-xxxx-xxxx-xxxx shape: only the exact-value redaction can catch it
ENV_FILE_ONLY = "VALUE_THAT_LIVES_ONLY_IN_DOT_ENV_314159"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def event(summary_out: str, kind: str = "decision", ok: bool = True, summary_in: str = "x") -> dict:
    return {"ts": "2026-10-23T10:00:00Z", "run_id": "r", "agent": "harness", "kind": kind, "summary_in": summary_in,
            "summary_out": summary_out, "ok": ok, "model": None, "latency_ms": None}


@pytest.fixture
def data(tmp_path, monkeypatch) -> Path:
    for var in trace.SECRET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    d = tmp_path / "data"
    (d / "runs").mkdir(parents=True)
    return d


@pytest.fixture
def secrets_in_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", API_KEY)
    monkeypatch.setenv("BLUESKY_APP_PASSWORD", APP_PASSWORD)


# Scrubbing ----------------------------------------------------------------------------------------------------------

def test_real_unicode_passes_through_untouched():
    text = "a real café and “quotes” — …"
    assert export.scrub(text) == text


def test_scrub_hides_post_identifiers_but_keeps_the_sentence():
    text = f"published: {URI} cid {CID} by {DID}"
    out = export.scrub(text)
    assert out == "published: [post link] cid [cid] by [did]"


def test_bsky_link_only_for_a_real_post_uri():
    assert export.bsky_link(URI) == f"https://bsky.app/profile/{DID}/post/3myhe2q5j432a"
    for bad in (None, "", "dryrun://post_1/abc", "https://evil.example/x", URI + "/../x", f"at://{DID}/other.collection/1"):
        assert export.bsky_link(bad) is None


# Posts, learnings, runs ---------------------------------------------------------------------------------------------

def test_a_post_with_a_pending_and_a_published_row_is_one_post_with_a_link_and_no_raw_uri(data):
    write_jsonl(data / "approved.jsonl", [
        {"run_id": "r1", "post_id": "p1", "text": "hello", "dry_run": False, "status": "pending",
         "started_at": "2026-10-23T07:13:11+00:00"},
        {"run_id": "r1", "post_id": "p1", "text": "hello", "dry_run": False, "status": "published", "attempt": 1,
         "scores": {"voice": 5}, "reasons": {"voice": "“warm”"}, "uri": URI, "cid": CID,
         "posted_at": "2026-10-23T07:13:14+00:00"},
        {"run_id": "r2", "post_id": "p2", "text": "dry", "dry_run": True, "status": "published",
         "uri": "dryrun://p2/abc", "posted_at": "2026-10-23T08:00:00+00:00"},
        {"run_id": "r3", "post_id": "p3", "text": "nope", "status": "failed", "reason": "settled by hand"},
    ])
    out = export.build(data)
    posts = {p["post_id"]: p for p in out["posts"]}
    assert len(out["posts"]) == 3
    assert posts["p1"]["status"] == "published" and posts["p1"]["link"] == export.bsky_link(URI)
    assert posts["p1"]["reasons"] == {"voice": "“warm”"}
    assert posts["p2"]["link"] is None and posts["p2"]["dry_run"] is True
    assert out["overview"]["live_posts"] == 1  # the dry run and the failed row are not live posts
    dumped = json.dumps(out)
    assert "at://" not in dumped and CID not in dumped and '"did:' not in dumped


def test_a_legacy_row_without_a_status_counts_as_published(data):
    write_jsonl(data / "approved.jsonl", [{"run_id": "r", "post_id": "p", "text": "t", "uri": URI,
                                            "posted_at": "2026-10-22T09:29:50+00:00", "dry_run": False}])
    assert export.build(data)["posts"][0]["status"] == "published"


def test_learnings_flag_whether_they_have_signal(data):
    write_jsonl(data / "learnings.jsonl", [
        {"run_id": "r", "post_id": "p1", "metrics": {"likes": 0}, "insight": "Not enough data yet: x",
         "saved_at": "2026-10-23T10:00:00+00:00"},
        {"run_id": "r", "post_id": "p2", "metrics": {"likes": 5}, "insight": "Questions got replies.",
         "saved_at": "2026-10-24T10:00:00+00:00"}])
    out = export.build(data)
    assert [l["has_signal"] for l in out["learnings"]] == [True, False]  # newest first
    assert out["overview"]["learnings_with_signal"] == 1


def test_runs_are_summarised_and_an_unreadable_trace_is_reported_not_fatal(data):
    (data / "runs" / "run_a.json").write_text(json.dumps([
        event("start", summary_in="run_post"), event("m", kind="llm_call"), event("published", ok=True)]), "utf-8")
    (data / "runs" / "run_bad.json").write_text("{not json", "utf-8")
    (data / "runs" / "run_empty.json").write_text("[]", "utf-8")
    out = export.build(data)
    assert [r["run_id"] for r in out["runs"]] == ["run_a"]
    run = out["runs"][0]
    assert run["llm_calls"] == 1 and run["final"] == "published" and run["label"] == "run_post"
    assert out["overview"]["unreadable_traces"] == ["run_bad.json"]
    assert out["overview"]["llm_calls"] == 1


def test_a_runs_outcome_skips_the_run_summary_json(data):
    (data / "runs" / "run_o.json").write_text(json.dumps([
        event("start"), event("0 to measure; none skipped"),
        event('{"schema_version": 1}', summary_in="run_summary sha256=abc")]), "utf-8")
    assert export.build(data)["runs"][0]["final"] == "0 to measure; none skipped"


def test_the_sample_dry_run_trace_is_excluded_by_name_even_when_asked_for(data):
    for name in ("run_20261022_080056_bb7b95.json", "run_real.json"):
        (data / "runs" / name).write_text(json.dumps([event("x")]), "utf-8")
    assert [r["run_id"] for r in export.build(data)["runs"]] == ["run_real"]


def test_only_files_git_tracks_are_exported(tmp_path):
    repo = tmp_path / "repo"
    (repo / "data" / "runs").mkdir(parents=True)
    for name in ("run_tracked.json", "run_untracked.json"):
        (repo / "data" / "runs" / name).write_text(json.dumps([event("x")]), "utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "data/runs/run_tracked.json"], cwd=repo, check=True)
    tracked = export.tracked_files(repo, repo / "data")
    assert tracked is not None
    assert [r["run_id"] for r in export.build(repo / "data", tracked)["runs"]] == ["run_tracked"]


def test_a_data_dir_outside_the_repo_means_no_git_filter(tmp_path):
    assert export.tracked_files(Path(trace.REPO_ROOT), tmp_path) is None


def test_the_overview_says_what_is_partial(data):
    (data / "calibration").mkdir()
    (data / "calibration" / "report.partial-run_x.md").write_text(
        "- Drafts: 10 in the file, 7 scored by the critic, 10 with your scores\n", "utf-8")
    partial = " ".join(export.build(data)["overview"]["partial"])
    for fragment in ("7 of 10", "scheduled", "planner", "real model"):
        assert fragment in partial


def test_a_complete_calibration_report_states_the_result(data):
    (data / "calibration").mkdir()
    (data / "calibration" / "report.md").write_text(
        "- Agreement: **6 of 10** (60%)\n- Critic passes a draft you would fail (too lenient): 4 (d03, d06, d08, d10)\n", "utf-8")
    partial = " ".join(export.build(data)["overview"]["partial"])
    assert "complete" in partial and "6 of 10" in partial and "d03, d06, d08, d10" in partial
    assert "is partial" not in partial


# Secrets ------------------------------------------------------------------------------------------------------------

def test_no_secret_value_reaches_the_output_files(data, tmp_path, secrets_in_env, monkeypatch):
    """Secrets planted in every place text is read from: trace events, the post log and the learnings."""
    (tmp_path / ".env").write_text(f"OPENROUTER_API_KEY={API_KEY}\nOTHER={ENV_FILE_ONLY}\n", encoding="utf-8")
    (data / ".env").write_text(f"X={ENV_FILE_ONLY}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    leak = f"Authorization: Bearer {API_KEY} and password {APP_PASSWORD} and {URI}"
    (data / "runs" / "run_leak.json").write_text(json.dumps([
        event(leak, kind="llm_call", summary_in=leak), event(leak, kind="tool_call")]), "utf-8")
    write_jsonl(data / "approved.jsonl", [{"run_id": "r", "post_id": "p", "text": leak, "status": "published",
                                            "reasons": {"voice": leak}, "reason": leak, "uri": URI,
                                            "posted_at": "2026-10-23T07:13:14+00:00"}])
    write_jsonl(data / "learnings.jsonl", [{"run_id": "r", "post_id": "p", "metrics": {}, "insight": leak,
                                             "saved_at": "2026-10-23T10:00:00+00:00"}])
    out_dir = tmp_path / "site"
    paths = export.write(export.build(data), out_dir)
    assert {p.name for p in paths} == {"data.json", "data.js"}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for secret in (API_KEY, APP_PASSWORD, ENV_FILE_ONLY, "sk-or-"):
            assert secret not in text, f"{secret[:6]}... found in {path.name}"
        assert "at://" not in text and DID not in text.replace(f"https://bsky.app/profile/{DID}/post/", "")
    assert "[REDACTED" in (out_dir / "data.json").read_text(encoding="utf-8")  # it was replaced, not dropped silently


def test_the_final_gate_refuses_a_secret_that_got_past_the_scrubbing(secrets_in_env):
    with pytest.raises(ValueError, match="secret"):
        export.check_safe(json.dumps({"text": f"oops {APP_PASSWORD}"}))
    with pytest.raises(ValueError, match="raw"):
        export.check_safe(json.dumps({"text": URI}))
    with pytest.raises(ValueError, match="raw"):
        export.check_safe(json.dumps({"did": DID}))
    export.check_safe(json.dumps({"link": export.bsky_link(URI)}))  # the link form is allowed


def test_write_refuses_and_leaves_no_file_when_the_gate_fails(tmp_path, secrets_in_env):
    out_dir = tmp_path / "site"
    with pytest.raises(ValueError):
        export.write({"schema_version": 1, "leak": URI}, out_dir)
    assert not out_dir.exists()


def test_the_script_never_opens_dot_env():
    """Reading .env here would be the way a real secret could get in; the source must not mention it."""
    source = Path(export.__file__).read_text(encoding="utf-8")
    assert "load_dotenv" not in source and 'open(".env' not in source and '".env"' not in source


# The real repo data -------------------------------------------------------------------------------------------------

def test_the_repos_own_data_exports_cleanly_and_without_the_sample_trace():
    out = export.build(trace.REPO_ROOT / "data", export.tracked_files(trace.REPO_ROOT, trace.REPO_ROOT / "data"))
    export.check_safe(json.dumps(out, ensure_ascii=False))
    assert "run_20261022_080056_bb7b95" not in {r["run_id"] for r in out["runs"]}
    assert out["overview"]["live_posts"] >= 2
