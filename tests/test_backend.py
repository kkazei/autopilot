"""backend/app.py: the secret, one run at a time, approvals over HTTP, and a full hosted run against MemoryStore."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import app as backend
from harness import trace
from harness.llm import MockLLM
from mcp_server import server
from scripts import run_outer
from tests.helpers import GOOD_TEXT, NOW, scores, week_json
from tests.memory_store import MemoryStore
from tests.test_outer_loop import bsky  # noqa: F401
from ui.controller import Controller

SECRET = "s" * 40
HEADERS = {backend.SECRET_HEADER: SECRET}
REPO_ROOT = Path(__file__).resolve().parent.parent


def client_for(ctl: Controller) -> TestClient:
    return TestClient(backend.create_app(controller=ctl, secret=SECRET))


def wait_status(client: TestClient, cond, timeout_s: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        s = client.get("/status", headers=HEADERS).json()
        if cond(s):
            return s
        time.sleep(0.02)
    raise AssertionError(f"condition not met; last status: {s}")


def finished(s: dict) -> bool:
    return not s["running"] and s["exit_code"] is not None


def test_refuses_to_start_without_a_long_secret(monkeypatch):
    monkeypatch.delenv(backend.SECRET_ENV, raising=False)
    with pytest.raises(RuntimeError, match="at least 32"):
        backend.create_app(controller=Controller(), secret="short")
    with pytest.raises(RuntimeError):
        backend.create_app(controller=Controller())


def test_every_route_but_health_needs_the_secret():
    client = client_for(Controller(runner=lambda a, i, s: 0))
    assert client.get("/health").json() == {"ok": True}
    for method, path in [("get", "/status"), ("post", "/runs"), ("post", "/approvals/1"),
                         ("post", "/posts/p/requeue")]:
        assert getattr(client, method)(path).status_code == 401
        assert getattr(client, method)(path, headers={backend.SECRET_HEADER: "s" * 39}).status_code == 401
    assert client.get("/docs").status_code == 404  # no public API docs on the Space


def test_run_kinds_map_to_controller_arguments_and_approval_cannot_be_turned_off():
    seen: list[list[str]] = []
    ctl = Controller(runner=lambda a, i, s: seen.append(a) or 0, post_runner=lambda a, i, s: seen.append(a) or 0)
    client = client_for(ctl)
    for body in ({"kind": "next", "dry_run": True}, {"kind": "plan"},
                 {"kind": "topic", "topic": "Bread", "goal": "click"}):
        assert client.post("/runs", json=body, headers=HEADERS).status_code == 202
        wait_status(client, finished)
    assert seen == [["--dry-run"], ["--plan-only"], ["--topic", "Bread", "--goal", "click"]]
    assert not any("--no-approve" in a for a in seen)
    bad = client.post("/runs", json={"kind": "next", "approve": False, "argv": ["--no-approve"]}, headers=HEADERS)
    assert bad.status_code == 202 and seen[-1] == []  # unknown fields are ignored, never passed through
    assert client.post("/runs", json={"kind": "topic", "topic": "  "}, headers=HEADERS).status_code == 422
    assert client.post("/runs", json={"kind": "measure"}, headers=HEADERS).status_code == 422


def test_a_second_run_and_a_stale_approval_are_refused():
    release = threading.Event()
    answers: list[str] = []

    def runner(argv, input_fn, say):
        answers.append(input_fn("Publish this post? [y/N] "))
        release.wait(5)
        return 0
    client = client_for(Controller(runner=runner))
    assert client.post("/runs", json={"kind": "next"}, headers=HEADERS).status_code == 202
    s = wait_status(client, lambda s: s["approval"] is not None)
    assert client.post("/runs", json={"kind": "next"}, headers=HEADERS).status_code == 409
    assert client.post("/posts/p/requeue", headers=HEADERS).status_code == 409
    assert client.post(f"/approvals/{s['approval']['id'] + 1}", json={"choice": "approve"},
                       headers=HEADERS).status_code == 409
    assert client.post(f"/approvals/{s['approval']['id']}", json={"choice": "approve"},
                       headers=HEADERS).json() == {"message": "Approved."}
    assert client.post(f"/approvals/{s['approval']['id']}", json={"choice": "reject"},
                       headers=HEADERS).status_code == 409  # answered once only
    release.set()
    wait_status(client, finished)
    assert answers == ["y"]


def test_busy_store_is_reported_as_another_run(monkeypatch):
    store = MemoryStore()
    store.locked = True  # the cron holds the lock
    ctl = Controller(runner=backend.hosted_runner(lambda a, i, s: pytest.fail("must not run"), lambda: store))
    client = client_for(ctl)
    client.post("/runs", json={"kind": "next"}, headers=HEADERS)
    s = wait_status(client, finished)
    assert s["exit_code"] == backend.EXIT_BUSY and "another hosted run is active" in s["log"]


@pytest.fixture
def hosted_env(monkeypatch, tmp_path):
    monkeypatch.delenv(trace.DATA_DIR_ENV, raising=False)
    monkeypatch.setenv(server.CALL_LOG_ENV, str(tmp_path / "calls.jsonl"))
    for var in (server.ROLE_ENV, server.TOKEN_ENV, server.DRY_RUN_ENV):
        monkeypatch.delenv(var, raising=False)


def test_a_live_hosted_run_plans_waits_for_approval_publishes_and_lands_in_the_store(hosted_env, bsky):  # noqa: F811
    store = MemoryStore()
    store.docs["brand_brief.json"] = json.loads((REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))

    def outer(argv, input_fn, say):
        llm = MockLLM([week_json(), GOOD_TEXT, scores(5)])
        return run_outer.main(argv, llm=llm, input_fn=input_fn, now=NOW, env_file=None, say=say)
    client = client_for(Controller(runner=backend.hosted_runner(outer, lambda: store)))

    assert client.post("/runs", json={"kind": "next"}, headers=HEADERS).status_code == 202
    s = wait_status(client, lambda s: s["approval"] is not None)
    assert "Publish this post?" in s["approval"]["prompt"] and bsky == []
    deadline = time.monotonic() + 10
    while not store.runs and time.monotonic() < deadline:
        time.sleep(0.05)
    assert store.runs, "the trace is pushed live while the run waits for approval"
    client.post(f"/approvals/{s['approval']['id']}", json={"choice": "approve"}, headers=HEADERS)
    s = wait_status(client, finished)

    assert s["exit_code"] == 0 and len(bsky) == 1
    published = [r for r in store.logs["approved.jsonl"] if r.get("status") == "published"]
    assert len(published) == 1 and published[0]["uri"].startswith("at://")
    assert [p["status"] for p in store.docs["plan_state.json"]["posts"]][0] == "published"
    events = next(iter(store.runs.values()))[1]
    assert any(e["kind"] == "llm_call" for e in events) and events[-1]["summary_in"].startswith("run_summary")
    assert not store.locked
