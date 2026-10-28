"""Postgres as the source of truth: pull, run the unchanged harness on files, push back, under one lock."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from harness import db_sync, quota, trace
from harness.db_sync import LivePusher, StoreBusy, SyncError, hosted_data_dir, pull, push
from harness.fileio import append_jsonl
from scripts import db_import, db_run
from tests.memory_store import MemoryStore

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
BRIEF = json.loads((REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))


def event(ts: datetime, kind: str = "llm_call") -> dict:
    return {"ts": ts.isoformat(), "run_id": "r", "agent": "writer", "kind": kind, "summary_in": "i",
            "summary_out": "o", "ok": True, "model": None, "latency_ms": None}


def seeded() -> MemoryStore:
    store = MemoryStore()
    store.docs["brand_brief.json"] = BRIEF
    store.logs["approved.jsonl"] = [{"run_id": "r0", "post_id": "a", "status": "published", "text": "old"}]
    store.runs["run_20261028_100000_aaaaaa"] = (NOW - timedelta(hours=2), [event(NOW - timedelta(hours=2))])
    store.runs["run_20261020_100000_bbbbbb"] = (NOW - timedelta(days=8), [event(NOW - timedelta(days=8))])
    return store


@pytest.fixture(autouse=True)
def _restore_data_dir(monkeypatch):
    """hosted_data_dir sets the variable itself; the test must leave the process as it found it."""
    monkeypatch.delenv(trace.DATA_DIR_ENV, raising=False)


def test_pull_writes_the_harness_layout_with_only_recent_traces(tmp_path):
    pull(seeded(), tmp_path, NOW)
    assert json.loads((tmp_path / "brand_brief.json").read_text(encoding="utf-8")) == BRIEF
    assert not (tmp_path / "plan_state.json").exists()  # nothing stored yet: the harness starts a fresh plan
    assert json.loads((tmp_path / "approved.jsonl").read_text(encoding="utf-8").splitlines()[0])["post_id"] == "a"
    assert (tmp_path / "learnings.jsonl").read_text(encoding="utf-8") == ""
    assert [p.name for p in (tmp_path / "runs").iterdir()] == ["run_20261028_100000_aaaaaa.json"]


def test_pulled_traces_feed_the_quota_count(tmp_path):
    pull(seeded(), tmp_path, NOW)
    used, unreadable = quota.llm_calls_since(NOW - quota.WINDOW, tmp_path / "runs")
    assert (used, unreadable) == (1, 0)


def test_quota_limit_is_the_hard_cap_of_45():
    assert quota.DAILY_REQUEST_LIMIT == 45


def test_push_appends_only_new_log_records_and_changed_docs(tmp_path):
    store = seeded()
    pull(store, tmp_path, NOW)
    append_jsonl(tmp_path / "approved.jsonl", {"run_id": "r1", "post_id": "b", "status": "published", "text": "new"})
    (tmp_path / "plan_state.json").write_text(json.dumps({"schema_version": 1, "plans": [], "posts": []}),
                                              encoding="utf-8")
    report = push(store, tmp_path)
    assert [r["post_id"] for r in store.logs["approved.jsonl"]] == ["a", "b"]
    assert report.appended == {"approved.jsonl": 1, "learnings.jsonl": 0, "measurements.jsonl": 0}
    assert report.docs == ["plan_state.json"]  # the brief was unchanged, so it is not rewritten


def test_push_refuses_a_log_that_lost_or_changed_a_stored_record(tmp_path):
    store = seeded()
    pull(store, tmp_path, NOW)
    (tmp_path / "approved.jsonl").write_text("", encoding="utf-8")  # a stale or broken copy
    with pytest.raises(SyncError, match="approved.jsonl no longer starts with"):
        push(store, tmp_path)
    assert len(store.logs["approved.jsonl"]) == 1


def test_push_refuses_unreadable_lines_but_still_saves_the_traces(tmp_path):
    store = seeded()
    pull(store, tmp_path, NOW)
    with (tmp_path / "approved.jsonl").open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    (tmp_path / "runs" / "run_20261028_110000_cccccc.json").write_text(json.dumps([event(NOW)]), encoding="utf-8")
    with pytest.raises(SyncError, match="1 unreadable line"):
        push(store, tmp_path)
    assert "run_20261028_110000_cccccc" in store.runs


def test_pull_rejects_a_run_id_that_could_escape_the_folder(tmp_path):
    store = MemoryStore()
    store.runs["../evil"] = (NOW, [])
    with pytest.raises(SyncError, match="invalid run id"):
        pull(store, tmp_path, NOW)


def test_run_start_comes_from_the_id_or_falls_back_to_the_first_event():
    assert db_sync.run_started_at("run_20261028_093000_abcdef", []) == datetime(2026, 10, 28, 9, 30, tzinfo=timezone.utc)
    assert db_sync.run_started_at("demo_run", [event(NOW)]) == NOW


def test_a_hosted_run_reads_and_writes_the_working_folder_then_lands_in_the_store(tmp_path):
    store = seeded()
    with hosted_data_dir(store, tmp_path, now=NOW) as work:
        assert store.locked and trace.data_dir() == work
        run_id = trace.start_run()
        trace.log_event(run_id, "harness", "decision", "start", "ok", ok=True)
        append_jsonl(work / "learnings.jsonl", {"run_id": run_id, "post_id": "a", "metrics": {}, "insight": "x"})
    assert not store.locked and trace.DATA_DIR_ENV not in os.environ
    assert store.runs[run_id][1][0]["summary_in"] == "start"
    assert store.logs["learnings.jsonl"][0]["insight"] == "x"


def test_a_failed_run_still_pushes_its_trace_and_releases_the_lock(tmp_path):
    store = seeded()
    with pytest.raises(RuntimeError, match="boom"):
        with hosted_data_dir(store, tmp_path, now=NOW):
            run_id = trace.start_run()
            raise RuntimeError("boom")
    assert run_id in store.runs and not store.locked


def test_a_second_hosted_run_is_refused_while_one_holds_the_lock(tmp_path):
    store = seeded()
    store.locked = True
    with pytest.raises(StoreBusy):
        with hosted_data_dir(store, tmp_path, now=NOW):
            pytest.fail("must not run")
    assert not (tmp_path / "approved.jsonl").exists()  # nothing pulled either
    assert store.locked  # the other run's lock is left alone


def test_live_pusher_sends_changed_traces_while_the_run_is_going(tmp_path):
    store = MemoryStore()
    (tmp_path / "runs").mkdir()
    path = tmp_path / "runs" / "run_20261028_110000_dddddd.json"
    path.write_text(json.dumps([event(NOW)]), encoding="utf-8")
    pusher = LivePusher(store, tmp_path, interval_s=0.01)
    pusher.start()
    try:
        deadline = time.monotonic() + 5
        while "run_20261028_110000_dddddd" not in store.runs and time.monotonic() < deadline:
            time.sleep(0.01)
        calls = store.put_run_calls
        time.sleep(0.1)
        assert store.put_run_calls == calls  # an unchanged file is not sent again
    finally:
        pusher.stop()
    assert "run_20261028_110000_dddddd" in store.runs and pusher.failures == 0


def test_db_run_passes_arguments_through_and_maps_busy_and_unsaved(tmp_path):
    seen: list[list[str]] = []
    assert db_run.main(["--measure-only"], store=seeded(), runner=lambda a: seen.append(a) or 0) == 0
    assert seen == [["--measure-only"]]
    busy = seeded()
    busy.locked = True
    assert db_run.main([], store=busy, runner=lambda a: 0) == db_run.EXIT_BUSY

    def corrupt(_args: list[str]) -> int:
        (trace.data_dir() / "approved.jsonl").write_text("", encoding="utf-8")
        return 0
    assert db_run.main([], store=seeded(), runner=corrupt) == db_run.EXIT_NOT_SAVED


def test_db_import_copies_the_repo_data_and_is_safe_to_repeat(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(REPO_ROOT / "data" / "brand_brief.json", data / "brand_brief.json")
    append_jsonl(data / "approved.jsonl", {"run_id": "r0", "post_id": "a", "status": "published"})
    (data / "runs").mkdir()
    (data / "runs" / "run_20261028_100000_eeeeee.json").write_text(json.dumps([event(NOW)]), encoding="utf-8")
    store = MemoryStore()
    assert db_import.main(["--data-dir", str(data)], store=store) == 0
    assert db_import.main(["--data-dir", str(data)], store=store) == 0
    assert len(store.logs["approved.jsonl"]) == 1 and store.docs["brand_brief.json"] == BRIEF
    assert "run_20261028_100000_eeeeee" in store.runs and not store.locked
    assert "approved.jsonl +0" in capsys.readouterr().out.splitlines()[-1]


def test_database_urls_are_redacted_from_traces(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://owner:s3cret-pass@ep-x.neon.tech/autopilot?sslmode=require")
    assert "s3cret-pass" not in trace.redact("connect failed: postgresql://owner:s3cret-pass@ep-x.neon.tech/autopilot?sslmode=require")
    monkeypatch.delenv("DATABASE_URL")
    out = trace.redact("dsn postgres://app:other-pass@host/db")
    assert "other-pass" not in out and "postgres://app:[REDACTED]@host/db" in out
