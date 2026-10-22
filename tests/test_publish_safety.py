"""Publish-path safety (review items 1-4): a real post is never lost or double-counted, and publish re-checks itself.

Each test reproduces one reviewed failure through scripts/run_post.py with a fake Bluesky client.
MockLLM and temp data dirs only; no network.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import harness.publish as publish_mod
from harness import trace
from harness.fileio import read_jsonl
from harness.llm import MockLLM
from harness.publish import PublishBlocked, approved_path, publish
from harness.schemas import BrandBrief, Critique, Draft
from mcp_server import bluesky, server
from scripts import run_post

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
GOOD = json.dumps({"text": "Saturday's class starts with flour on your hands. Save a seat at the link."})
OTHER = json.dumps({"text": "Rye on Sunday: a darker crust, a slower rise, and a seat for you if you want one."})
REASONS = {d: f"{d} is fine." for d in ("voice", "clarity", "cta", "policy_risk")}
SCORES = json.dumps({"voice": 5, "clarity": 5, "cta": 5, "policy_risk": 5, "reasons": REASONS})


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch) -> Path:
    shutil.copy(REPO_ROOT / "data" / "brand_brief.json", tmp_path / "brand_brief.json")
    monkeypatch.setenv(trace.DATA_DIR_ENV, str(tmp_path))
    monkeypatch.setenv(server.CALL_LOG_ENV, str(tmp_path / "calls.jsonl"))
    for var in (server.ROLE_ENV, server.TOKEN_ENV, server.DRY_RUN_ENV):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def bsky(monkeypatch) -> list[str]:
    sent: list[str] = []

    def fake_post(text):
        sent.append(text)
        return {"uri": f"at://did:plc:test/app.bsky.feed.post/{len(sent)}", "cid": f"c{len(sent)}"}

    monkeypatch.setattr(bluesky, "post", fake_post)
    return sent


def run(script, answers=("y",), now=NOW, input_fn=None):
    queue = list(answers)

    def default_input(prompt: str) -> str:
        if not queue:
            raise EOFError
        return queue.pop(0)

    llm = MockLLM(list(script))
    code = run_post.main(["--topic", "Saturday class"], llm=llm, input_fn=input_fn or default_input,
                         now=now, env_file=None)
    return code, llm


def write_approved(*rows: dict) -> None:
    approved_path().parent.mkdir(parents=True, exist_ok=True)
    with approved_path().open("a", encoding="utf-8") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)


# ---------- item 1: a live post is never lost ----------

def test_call_log_failure_after_a_real_post_is_not_reported_as_failed(env, bsky, monkeypatch):
    real_append = server.append_jsonl

    def flaky(path, record):
        if record.get("tool") == "publish_post" and record.get("ok") is True:
            raise OSError("disk full")
        real_append(path, record)

    monkeypatch.setattr(server, "append_jsonl", flaky)
    code, _ = run([GOOD, SCORES])
    assert code == run_post.EXIT_PUBLISHED and len(bsky) == 1
    assert any(r.get("uri", "").startswith("at://") for r in read_jsonl(approved_path())[0])


def test_lost_approved_row_still_blocks_the_next_run(env, bsky, monkeypatch):
    real_append = publish_mod.append_jsonl

    def flaky(path, record):
        if "uri" in record:
            raise OSError("disk full")
        real_append(path, record)

    monkeypatch.setattr(publish_mod, "append_jsonl", flaky)
    code, _ = run([GOOD, SCORES])
    assert code == run_post.EXIT_PUBLISHED and len(bsky) == 1
    monkeypatch.setattr(publish_mod, "append_jsonl", real_append)
    code, llm = run([OTHER, SCORES], now=NOW + timedelta(minutes=5))
    assert code == run_post.EXIT_BLOCKED and len(bsky) == 1 and llm.calls == []


def test_unknown_publish_outcome_keeps_counting_toward_the_cap(env, monkeypatch):
    def reset_after_send(text):
        raise bluesky.BlueskyError("connection reset after the request was sent")

    monkeypatch.setattr(bluesky, "post", reset_after_send)
    code, _ = run([GOOD, SCORES])
    assert code == run_post.EXIT_FAILED
    code, llm = run([OTHER, SCORES], now=NOW + timedelta(minutes=5))
    assert code == run_post.EXIT_BLOCKED and llm.calls == []


# ---------- item 2: an unreadable approved.jsonl fails closed ----------

def test_unreadable_approved_line_blocks_publishing(env, bsky):
    approved_path().write_text('{"text": "half a reco\n', encoding="utf-8")
    code, llm = run([GOOD, SCORES])
    assert code == run_post.EXIT_BLOCKED and bsky == [] and llm.calls == []


# ---------- item 3: publish re-checks the exact text itself ----------

def test_publish_rechecks_even_when_the_callers_gate_says_ok(env, bsky, monkeypatch):
    banned = json.dumps({"text": "Act now: the best bakery in town has seats."})
    monkeypatch.setattr(run_post.guardrails, "run_all",
                        lambda *a, **k: {"ok": True, "reasons": [], "checks": {}})
    code, _ = run([banned, SCORES])
    assert code == run_post.EXIT_BLOCKED and bsky == []


# ---------- item 4: no double publish across the approval wait ----------

def test_post_by_another_run_during_approval_wait_blocks_this_one(env, bsky):
    def approve_while_another_run_posts(prompt: str) -> str:
        write_approved({"text": "another run's post", "posted_at": NOW.isoformat(), "uri": "at://x/1",
                        "dry_run": False})
        return "y"

    code, _ = run([GOOD, SCORES], input_fn=approve_while_another_run_posts)
    assert code == run_post.EXIT_BLOCKED and bsky == []


# ---------- publish() directly ----------

BRIEF = BrandBrief.model_validate_json((REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))
CRIT = Critique(voice=5, clarity=5, cta=5, policy_risk=5, reasons=REASONS)


def draft(post_id: str, text: str = "Warm rye on Saturday, and a seat for you if you want one.") -> Draft:
    return Draft(post_id=post_id, text=text, attempt=1)


def test_two_overlapping_publishes_only_one_goes_out(env, monkeypatch):
    """Both callers passed their own checks; the lock and re-check let exactly one through."""
    sent: list[str] = []
    entered = threading.Event()

    def slow_post(text):
        entered.set()
        time.sleep(0.3)  # the second caller arrives while this one is mid-post
        sent.append(text)
        return {"uri": f"at://x/{len(sent)}", "cid": "c"}

    monkeypatch.setattr(bluesky, "post", slow_post)
    results: dict[str, object] = {}

    def go(name: str, text: str) -> None:
        try:
            # Real clock: the server stamps posted_at with real time, so a pinned future clock would skew the gap.
            results[name] = publish(trace.start_run(), draft(name, text), CRIT, BRIEF, approved=True, dry_run=False)
        except PublishBlocked as e:
            results[name] = e

    first = threading.Thread(target=go, args=("p_a", "Warm rye on Saturday, come knead with us."))
    first.start()
    entered.wait(5)
    second = threading.Thread(target=go, args=("p_b", "Sunday focaccia, dimpled by hand, a seat for you."))
    second.start()
    first.join(10)
    second.join(10)
    assert len(sent) == 1
    assert isinstance(results["p_b"], PublishBlocked) and "minimum gap" in str(results["p_b"])


def test_lock_covers_the_gap_between_recheck_and_pending_row(env, monkeypatch):
    """Without the lock, two runs could both re-check before either writes its pending row."""
    sent: list[str] = []
    monkeypatch.setattr(bluesky, "post", lambda text: sent.append(text) or {"uri": f"at://x/{len(sent)}", "cid": "c"})
    real_recheck = publish_mod.recheck

    def slow_recheck(*args, **kwargs):
        reasons = real_recheck(*args, **kwargs)
        time.sleep(0.3)  # widen the window between the check and the write
        return reasons

    monkeypatch.setattr(publish_mod, "recheck", slow_recheck)
    texts = ["Warm rye on Saturday, come knead with us.", "Sunday focaccia, dimpled by hand, a seat for you."]
    outcomes: list[object] = []

    def go(i: int) -> None:
        try:
            outcomes.append(publish(trace.start_run(), draft(f"p{i}", texts[i]), CRIT, BRIEF, approved=True,
                                    dry_run=False))
        except PublishBlocked as e:
            outcomes.append(e)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert len(sent) == 1 and sum(isinstance(o, PublishBlocked) for o in outcomes) == 1


def test_run_post_hands_publish_a_live_clock(env, bsky):
    """The approval wait can be long; the pending row must carry the time of the post, not of the start."""
    times = iter([NOW, NOW + timedelta(minutes=30)])
    code = run_post.main(["--topic", "Saturday class"], llm=MockLLM([GOOD, SCORES]), input_fn=lambda p: "y",
                         clock=lambda: next(times), env_file=None)
    assert code == run_post.EXIT_PUBLISHED
    [pending] = [r for r in read_jsonl(approved_path())[0] if r.get("status") == "pending"]
    assert pending["started_at"] == (NOW + timedelta(minutes=30)).isoformat()


def test_publish_reads_a_fresh_clock_after_approval(env, bsky):
    """run_post's `now` is taken before the model calls and the approval wait; publish must not reuse it."""
    write_approved({"text": "earlier post", "posted_at": (NOW - timedelta(minutes=50)).isoformat(), "uri": "at://e"})
    with pytest.raises(PublishBlocked):  # at NOW the 60-minute gap is not over
        publish(trace.start_run(), draft("p1"), CRIT, BRIEF, approved=True, dry_run=False, clock=lambda: NOW)
    later = NOW + timedelta(minutes=15)  # the approval wait took 15 minutes
    record = publish(trace.start_run(), draft("p2"), CRIT, BRIEF, approved=True, dry_run=False, clock=lambda: later)
    pending = [r for r in read_jsonl(approved_path())[0] if r.get("status") == "pending"]
    assert record["uri"] and pending[-1]["started_at"] == later.isoformat()


def test_refused_send_settles_its_pending_row(env, monkeypatch):
    def bad_login(text):
        raise bluesky.BlueskyAuthError("Bluesky rejected the credentials")

    monkeypatch.setattr(bluesky, "post", bad_login)
    with pytest.raises(bluesky.BlueskyAuthError):
        publish(trace.start_run(), draft("p1"), CRIT, BRIEF, approved=True, dry_run=False, clock=lambda: NOW)
    statuses = [r["status"] for r in read_jsonl(approved_path())[0]]
    assert statuses == ["pending", "failed"] and publish_mod.live_records() == []


def test_live_records_counts_published_legacy_and_unsettled_rows_only(env):
    write_approved(
        {"text": "legacy row, no status", "posted_at": "2026-10-22T09:29:50+00:00", "run_id": "r0", "post_id": "a"},
        {"text": "settled", "status": "pending", "started_at": "2026-10-23T10:00:00+00:00", "run_id": "r1", "post_id": "b"},
        {"text": "settled", "status": "published", "posted_at": "2026-10-23T10:00:02+00:00", "run_id": "r1", "post_id": "b"},
        {"text": "unknown", "status": "pending", "started_at": "2026-10-23T11:00:00+00:00", "run_id": "r2", "post_id": "c"},
        {"text": "never sent", "status": "pending", "started_at": "2026-10-23T11:10:00+00:00", "run_id": "r3", "post_id": "d"},
        {"status": "failed", "run_id": "r3", "post_id": "d"},
        {"text": "rehearsal", "status": "published", "posted_at": "2026-10-23T11:20:00+00:00", "dry_run": True},
    )
    texts = sorted(r["text"] for r in publish_mod.live_records())
    assert texts == ["legacy row, no status", "settled", "unknown"]


def test_post_success_with_lost_bookkeeping_returns_warnings(env, bsky, monkeypatch):
    real_append = publish_mod.append_jsonl
    monkeypatch.setattr(publish_mod, "append_jsonl",
                        lambda p, r: (_ for _ in ()).throw(OSError("disk full")) if "uri" in r else real_append(p, r))
    real_log = publish_mod.trace.log_event

    def log_fails_after_post(run_id, agent, kind, summary_in, summary_out, ok, *a, **k):
        if kind == "tool_call" and ok:
            raise trace.TraceWriteError("trace gone")
        return real_log(run_id, agent, kind, summary_in, summary_out, ok, *a, **k)

    monkeypatch.setattr(publish_mod.trace, "log_event", log_fails_after_post)
    record = publish("run_x", draft("p1"), CRIT, BRIEF, approved=True, dry_run=False, clock=lambda: NOW)
    assert record["uri"] == "at://did:plc:test/app.bsky.feed.post/1" and len(record["warnings"]) == 2
