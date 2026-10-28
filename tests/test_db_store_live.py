"""PostgresStore against a real database. Skipped unless AUTOPILOT_TEST_DATABASE_URL names a throwaway database.

Use a separate Neon branch, never the one the app runs on: the test drops and recreates the three tables.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from harness import trace
from harness.db_store import URL_ENV, PostgresStore
from harness.env import load_dotenv

load_dotenv(trace.REPO_ROOT / ".env")  # values already in the environment win, as everywhere else
URL = os.environ.get("AUTOPILOT_TEST_DATABASE_URL")
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

pytestmark = [pytest.mark.live, pytest.mark.skipif(not URL, reason="AUTOPILOT_TEST_DATABASE_URL is not set")]


@pytest.fixture
def store():
    if URL == os.environ.get(URL_ENV):
        pytest.fail("AUTOPILOT_TEST_DATABASE_URL is the app's DATABASE_URL; this test drops tables, so refusing")
    s = PostgresStore(URL)
    s._conn.execute("drop table if exists docs, log_records, runs")
    s.close()
    s = PostgresStore(URL)
    yield s
    s.close()


def test_round_trips_docs_logs_and_runs(store):
    assert store.get_doc("plan_state.json") is None
    store.put_doc("plan_state.json", {"posts": [{"id": "p", "day": "2026-10-28"}]})
    store.put_doc("plan_state.json", {"posts": []})
    assert store.get_doc("plan_state.json") == {"posts": []}

    store.append_log("approved.jsonl", 0, [{"post_id": "a"}, {"post_id": "b"}])
    store.append_log("approved.jsonl", 2, [{"post_id": "c"}])
    assert [r["post_id"] for r in store.get_log("approved.jsonl")] == ["a", "b", "c"]
    with pytest.raises(Exception):  # a stale writer collides on (log, seq) instead of interleaving
        store.append_log("approved.jsonl", 1, [{"post_id": "x"}])
    assert len(store.get_log("approved.jsonl")) == 3

    store.put_run("run_new", NOW, [{"kind": "llm_call"}])
    store.put_run("run_new", NOW, [{"kind": "llm_call"}, {"kind": "decision"}])
    store.put_run("run_old", NOW - timedelta(days=5), [])
    assert store.runs_since(NOW - timedelta(days=1)) == {"run_new": [{"kind": "llm_call"}, {"kind": "decision"}]}


def test_the_advisory_lock_is_exclusive_across_connections(store):
    other = PostgresStore(URL)
    try:
        assert store.try_lock()
        assert not other.try_lock()
        store.unlock()
        assert other.try_lock()
        other.unlock()
    finally:
        other.close()
