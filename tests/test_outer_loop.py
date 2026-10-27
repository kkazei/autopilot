"""scripts/run_outer.py and loops/outer.py: the whole outer run against MockLLM and a fake Bluesky.

Covers the outcome-to-status table, the lock, the request caps and dry-run isolation."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import timedelta

import pytest

from harness import plan_state, quota, trace
from harness.fileio import read_jsonl
from harness.llm import LLMUnavailable, MockLLM
from harness.publish import approved_path
from loops import outer
from mcp_server import bluesky, server
from scripts import run_outer
from tests.helpers import (  # noqa: F401
    GOOD_TEXT,
    NOW,
    add_learning,
    add_published,
    data,
    insight_json,
    scores,
    week_json,
)

OTHER_TEXT = json.dumps({"text": "Rye loaves need patience: a slow rise gives the crust its deep colour. Read more below."})
PLAN_SCRIPT = [week_json()]
POST_SCRIPT = [GOOD_TEXT, scores(5)]


@pytest.fixture
def bsky(monkeypatch) -> list[str]:
    sent: list[str] = []

    def fake_post(text):
        sent.append(text)
        return {"uri": f"at://did:plc:test/app.bsky.feed.post/n{len(sent)}", "cid": "c1"}

    monkeypatch.setattr(bluesky, "post", fake_post)
    monkeypatch.setattr(bluesky, "get_post_metrics", lambda uri: {"likes": 0, "reposts": 0, "replies": 0})
    # publish_post stamps posted_at from the real clock while these tests pin the run's clock to NOW. Left alone,
    # the test passed only until NOW + 2h of real time went by, then every later run saw a post "from the future".
    monkeypatch.setattr(server, "_now", lambda: NOW.isoformat())
    return sent


def go(argv, script, answers=("y",), now=NOW):
    prompts: list[str] = []
    queue = list(answers)

    def input_fn(prompt: str) -> str:
        prompts.append(prompt)
        if not queue:
            raise EOFError
        return queue.pop(0)

    llm = MockLLM(list(script))
    code = run_outer.main(argv, llm=llm, input_fn=input_fn, now=now, env_file=None)
    return code, llm, prompts


def state() -> plan_state.PlanState:
    return plan_state.load_state()


def statuses() -> list[str]:
    return [p.status for p in state().posts]


def published_rows() -> list[dict]:
    return [r for r in read_jsonl(approved_path())[0] if r.get("status") == "published"]


def last_events(run_id_prefix: str = "") -> list:
    runs = sorted((trace.data_dir() / "runs").glob("run_*.json"))
    return trace.read_run(runs[-1].stem)


def run_summary() -> dict:
    return json.loads(last_events()[-1].summary_out)


def test_first_run_plans_then_publishes_the_first_due_post(data, bsky):  # noqa: F811
    code, llm, prompts = go([], PLAN_SCRIPT + POST_SCRIPT)
    assert code == 0 and len(bsky) == 1 and len(prompts) == 1
    assert statuses() == ["published", "planned", "planned"]
    first = state().posts[0]
    assert first.uri.startswith("at://") and first.history[-1].status == "published"
    assert [r["post_id"] for r in published_rows()] == [first.id]
    assert all(p.id.startswith("post_") for p in state().posts)
    assert len(llm.calls) == 3  # planner, writer, critic


def test_a_run_with_posts_waiting_makes_no_planner_call(data, bsky):  # noqa: F811
    go([], PLAN_SCRIPT + POST_SCRIPT)
    later = NOW + timedelta(days=2)  # day 2026-10-25 is due; the 60-minute gap has passed
    code, llm, _ = go([], [OTHER_TEXT, scores(5)], now=later)
    assert code == 0 and statuses() == ["published", "published", "planned"]
    assert len(llm.calls) == 2


def test_no_post_is_due_exits_zero_without_model_calls(data, bsky):  # noqa: F811
    go([], PLAN_SCRIPT + POST_SCRIPT)
    code, llm, _ = go([], [], now=NOW + timedelta(hours=3))  # next post is two days away
    assert code == 0 and llm.calls == [] and len(bsky) == 1


def test_no_headroom_measures_then_exits_zero_before_any_model_call(data, bsky):  # noqa: F811
    add_published("post_aaaa1111", timedelta(minutes=10))
    code, llm, _ = go([], [])
    assert code == 0 and llm.calls == [] and bsky == []
    assert not plan_state.state_path().exists()


def test_flags_no_approve_needs_dry_run(data):  # noqa: F811
    code, llm, _ = go(["--no-approve"], [])
    assert code == 2 and llm.calls == []


def test_run_outer_itself_refuses_approval_off_for_a_live_run(data, bsky, capsys):  # noqa: F811
    from harness.schemas import BrandBrief

    brief = BrandBrief.model_validate_json((data / "brand_brief.json").read_text(encoding="utf-8"))
    llm = MockLLM(list(PLAN_SCRIPT + POST_SCRIPT))
    code = outer.run_outer(llm, brief, outer.OuterOptions(approve=False), clock=lambda: NOW)
    assert code == outer.EXIT_REFUSED and llm.calls == [] and bsky == []
    assert not (data / "runs").exists() or not list((data / "runs").glob("run_*.json"))
    assert not plan_state.state_path().exists() and "dry run" in capsys.readouterr().out


def test_measure_only_learns_and_stops(data, bsky, monkeypatch):  # noqa: F811
    add_published("post_aaaa1111")
    monkeypatch.setattr(bluesky, "get_post_metrics", lambda uri: {"likes": 3, "reposts": 1, "replies": 0})
    code, llm, _ = go(["--measure-only"], [insight_json()])
    assert code == 0 and len(llm.calls) == 1 and bsky == []
    assert [r["post_id"] for r in read_jsonl(trace.data_dir() / "learnings.jsonl")[0]] == ["post_aaaa1111"]
    assert not plan_state.state_path().exists()


def test_the_planner_sees_the_learning_and_must_cite_it(data, bsky, monkeypatch):  # noqa: F811
    add_published("post_aaaa1111", timedelta(hours=30))
    add_learning("post_aaaa1111")
    cited = week_json(rationale="Replies came from class posts [learning:post_aaaa1111].")
    code, llm, _ = go([], [week_json(rationale="no cite"), cited, *POST_SCRIPT])
    assert code == 0 and len(llm.calls) == 4  # planner twice (one retry), writer, critic
    assert "post_aaaa1111" in llm.calls[0][1]["content"]


# --- outcome -> status ---------------------------------------------------------------------------------------

def test_escalation_is_terminal_until_a_person_requeues_it(data, bsky):  # noqa: F811
    weak = scores(2)
    code, llm, _ = go([], PLAN_SCRIPT + [GOOD_TEXT, weak] * 3)
    assert code == 3 and statuses()[0] == "escalated" and bsky == []
    post_id = state().posts[0].id
    code, _, _ = go([], [OTHER_TEXT, scores(5)], now=NOW + timedelta(days=2))  # picks the NEXT post, not the escalated one
    assert state().posts[0].status == "escalated" and state().posts[1].status == "published"
    assert go(["--requeue", post_id], [])[0] == 0 and state().posts[0].status == "carried_forward"
    assert go(["--requeue", post_id], [])[0] == 2  # no longer escalated


def test_a_human_who_declines_blocks_the_post_for_good(data, bsky):  # noqa: F811
    code, _, _ = go([], PLAN_SCRIPT + POST_SCRIPT, answers=("n",))
    assert code == 5 and statuses()[0] == "blocked" and bsky == []


def test_nobody_at_the_prompt_carries_the_post_forward(data, bsky):  # noqa: F811
    code, _, _ = go([], PLAN_SCRIPT + POST_SCRIPT, answers=())
    assert code == 5 and statuses()[0] == "carried_forward" and bsky == []


def test_a_banned_phrase_blocks_the_post(data, bsky):  # noqa: F811
    bad = json.dumps({"text": "Act now to join Saturday's class."})
    code, _, prompts = go([], PLAN_SCRIPT + [bad, scores(5)])
    assert code == 5 and statuses()[0] == "blocked" and prompts == [] and bsky == []


def test_a_model_failure_before_any_draft_is_retried_once_then_failed(data, bsky):  # noqa: F811
    down = [LLMUnavailable("all models failed")]
    assert go([], PLAN_SCRIPT + down)[0] == 4
    assert statuses()[0] == "carried_forward" and state().posts[0].runs_failed == 1
    assert go([], down, now=NOW + timedelta(hours=2))[0] == 4
    assert statuses()[0] == "failed"
    code, _, _ = go([], [OTHER_TEXT, scores(5)], now=NOW + timedelta(days=2))  # the next post is unaffected
    assert code == 0 and statuses()[1] == "published"


def test_a_planner_failure_exits_four_and_writes_no_state(data, bsky):  # noqa: F811
    code, _, _ = go([], [LLMUnavailable("down")])
    assert code == 4 and not plan_state.state_path().exists()


def test_an_unknown_publish_outcome_is_terminal_failed_and_never_retried(data, monkeypatch):  # noqa: F811
    def boom(text):
        raise ConnectionError("reset by peer")

    monkeypatch.setattr(bluesky, "post", boom)
    code, _, _ = go([], PLAN_SCRIPT + POST_SCRIPT)
    assert code == 4 and statuses()[0] == "failed"
    pending = [r for r in read_jsonl(approved_path())[0] if r["status"] == "pending"]
    assert len(pending) == 1  # still counts toward the rate cap


def test_a_post_already_in_the_approved_log_is_not_written_again(data, bsky, monkeypatch):  # noqa: F811
    real_save, saves = plan_state.save_state, []

    def save_fails_after_publish(s):
        saves.append(1)
        if len(saves) == 2:  # the first save stores the new plan; the second would record "published"
            raise OSError("disk full")
        real_save(s)

    monkeypatch.setattr(plan_state, "save_state", save_fails_after_publish)
    assert go([], PLAN_SCRIPT + POST_SCRIPT)[0] == 0 and len(bsky) == 1
    assert statuses()[0] == "planned"  # the live post's status was lost, like after a crash
    code, llm, _ = go([], [OTHER_TEXT, scores(5)], now=NOW + timedelta(hours=2))  # gap passed, day 1 still due
    assert code == 0 and len(bsky) == 1 and llm.calls == []
    first = state().posts[0]
    assert (first.status, first.uri) == ("published", "at://did:plc:test/app.bsky.feed.post/n1")


def test_the_rate_cap_at_publish_time_carries_the_post_forward(data, bsky, monkeypatch):  # noqa: F811
    real = outer.guardrails.run_all

    def gate_then_cap(*a, **kw):
        result = real(*a, **kw)
        add_published("post_zzzz9999", timedelta(minutes=1))  # someone else posted while we worked
        return result

    monkeypatch.setattr(outer.guardrails, "run_all", gate_then_cap)
    code, _, _ = go([], PLAN_SCRIPT + POST_SCRIPT)
    assert code == 5 and statuses()[0] == "carried_forward" and bsky == []


def test_the_run_request_cap_stops_cleanly_and_carries_the_post_forward(data, bsky, monkeypatch):  # noqa: F811
    monkeypatch.setattr(quota, "RUN_REQUEST_CAP", 2)  # planner takes 1, writer 1, then the critic has none
    code, llm, _ = go([], PLAN_SCRIPT + [GOOD_TEXT, scores(5)])
    assert code == 0 and bsky == [] and len(llm.calls) == 2
    first = state().posts[0]
    assert first.status == "carried_forward" and first.runs_failed == 0
    assert "request cap" in first.history[-1].reason
    assert run_summary()["requests"] == {"used": 2, "limit": 2}


def test_a_real_escalation_that_uses_the_last_request_is_still_escalated(data, bsky, monkeypatch):  # noqa: F811
    monkeypatch.setattr(quota, "RUN_REQUEST_CAP", 7)  # planner 1 + three writer/critic pairs: exactly the cap
    code, llm, _ = go([], PLAN_SCRIPT + [GOOD_TEXT, scores(2)] * 3)
    assert len(llm.calls) == 7 and code == 3 and statuses()[0] == "escalated"


def test_the_measurement_share_of_the_run_budget_is_capped(data, bsky, monkeypatch):  # noqa: F811
    for i in range(quota.MEASURE_REQUEST_CAP + 1):
        add_published(f"post_meas000{i}", timedelta(hours=5 + i))
    monkeypatch.setattr(bluesky, "get_post_metrics", lambda uri: {"likes": 3, "reposts": 0, "replies": 0})
    code, llm, _ = go(["--measure-only"], [insight_json()] * (quota.MEASURE_REQUEST_CAP + 1))
    assert code == 0 and len(llm.calls) == quota.MEASURE_REQUEST_CAP
    assert len(read_jsonl(trace.data_dir() / "learnings.jsonl")[0]) == quota.MEASURE_REQUEST_CAP


def test_the_daily_guard_blocks_every_model_call(data, bsky):  # noqa: F811
    stamps = [(NOW - timedelta(hours=1)).isoformat()] * 50
    events = [{"ts": t, "run_id": "r", "agent": "writer", "kind": "llm_call", "summary_in": "", "summary_out": "",
               "ok": True} for t in stamps]
    (data / "runs").mkdir()
    (data / "runs" / "run_old.json").write_text(json.dumps(events), encoding="utf-8")
    code, llm, _ = go([], PLAN_SCRIPT + POST_SCRIPT)
    assert code == 4 and llm.calls == [] and bsky == []


# --- lock ----------------------------------------------------------------------------------------------------

def test_a_second_run_is_refused_while_the_lock_is_held(data, bsky, capsys):  # noqa: F811
    lock = data / "outer_run.lock"
    lock.write_text("123")
    code, llm, _ = go([], PLAN_SCRIPT + POST_SCRIPT)
    assert code == 6 and llm.calls == [] and lock.exists()
    assert "delete" in capsys.readouterr().out


def test_a_lock_older_than_the_stale_time_is_taken_over_even_with_no_wait(data, bsky):  # noqa: F811
    lock = data / "outer_run.lock"
    lock.write_text("123")
    old = lock.stat().st_mtime - outer.OUTER_LOCK_STALE_S - 60
    os.utime(lock, (old, old))
    assert go([], PLAN_SCRIPT + POST_SCRIPT)[0] == 0
    assert not lock.exists()  # released at the end of the run


def test_a_lock_older_than_the_normal_stale_time_but_not_the_outer_one_still_blocks(data, bsky):  # noqa: F811
    lock = data / "outer_run.lock"
    lock.write_text("123")
    old = lock.stat().st_mtime - 3600  # a run waiting at the approval prompt for an hour is still running
    os.utime(lock, (old, old))
    assert go([], PLAN_SCRIPT + POST_SCRIPT)[0] == 6


def test_the_lock_is_released_after_a_run(data, bsky):  # noqa: F811
    go([], PLAN_SCRIPT + POST_SCRIPT)
    assert not (data / "outer_run.lock").exists()


# --- dry run -------------------------------------------------------------------------------------------------

def test_a_dry_run_writes_no_plan_state_no_learning_and_makes_no_reads(data, bsky, monkeypatch):  # noqa: F811
    add_published("post_aaaa1111", timedelta(hours=30))
    reads: list[str] = []
    monkeypatch.setattr(bluesky, "get_post_metrics", lambda uri: reads.append(uri) or {})
    code, llm, _ = go(["--dry-run", "--no-approve"], PLAN_SCRIPT + POST_SCRIPT)
    assert code == 0 and reads == [] and bsky == []
    assert not plan_state.state_path().exists()
    assert not (data / "learnings.jsonl").exists()
    assert len(llm.calls) == 3  # planner, writer, critic: no analyst
    rows = read_jsonl(approved_path())[0]
    assert [r["dry_run"] for r in rows[1:]] == [True, True] and published_rows()[-1]["dry_run"] is True
    assert any(e.summary_out.startswith("would measure") for e in last_events())


def test_a_dry_run_reads_the_real_plan_state(data, bsky):  # noqa: F811
    go([], PLAN_SCRIPT + POST_SCRIPT)
    before = plan_state.state_path().read_text(encoding="utf-8")
    code, llm, _ = go(["--dry-run", "--no-approve"], [OTHER_TEXT, scores(5)],
                      now=NOW + timedelta(days=2))
    assert code == 0 and len(llm.calls) == 2  # used the saved plan: no planner call
    assert plan_state.state_path().read_text(encoding="utf-8") == before


# --- trace ---------------------------------------------------------------------------------------------------

def test_the_run_trace_ends_with_a_hashed_untruncated_json_summary(data, bsky, monkeypatch):  # noqa: F811
    monkeypatch.setattr(trace, "SUMMARY_MAX_CHARS", 50)  # far below the summary's length: it must not be cut
    go([], PLAN_SCRIPT + POST_SCRIPT)
    events = last_events()
    final = events[-1]
    assert final.summary_in.startswith("run_summary sha256=")
    assert hashlib.sha256(final.summary_out.encode("utf-8")).hexdigest() == final.summary_in.split("=", 1)[1]
    summary = json.loads(final.summary_out)
    assert {"schema_version", "run_id", "plan", "outcomes", "learnings", "warnings"} <= set(summary)
    assert (summary["schema_version"], summary["run_id"], summary["exit_code"]) == (1, final.run_id, 0)
    assert [p["id"] for p in summary["plan"]["posts"]] == [p.id for p in state().posts]
    (outcome,) = summary["outcomes"]
    assert (outcome["post_id"], outcome["status"]) == (state().posts[0].id, "published")
    assert outcome["uri"].startswith("at://") and summary["requests"] == {"used": 3, "limit": 16}
    kinds = {(e.agent, e.kind) for e in events}
    assert {("planner", "llm_call"), ("writer", "llm_call"), ("critic", "llm_call"),
            ("harness", "decision"), ("harness", "tool_call")} <= kinds



def plan_only_summary() -> dict:
    """run_summary() takes the last file by name, and two runs in one second sort by their random suffix."""
    runs = [trace.read_run(f.stem) for f in (trace.data_dir() / "runs").glob("run_*.json")]
    events = next(e for e in runs if e[0].summary_in == "plan_now")
    return json.loads(events[-1].summary_out)

def test_plan_only_plans_and_saves_the_week_without_writing_or_measuring(data, bsky, monkeypatch):  # noqa: F811
    add_published("post_aaaa1111", timedelta(days=3))  # old enough to measure, but plan-only must not
    monkeypatch.setattr(bluesky, "get_post_metrics", lambda uri: pytest.fail("plan-only must not measure"))
    code, llm, prompts = go(["--plan-only"], PLAN_SCRIPT)
    assert code == 0 and len(llm.calls) == 1 and prompts == [] and bsky == []
    assert statuses() == ["planned", "planned", "planned"]
    assert plan_only_summary()["outcomes"] == [{"post_id": None, "status": "planned", "reason": "planned 3 posts"}]
    # The next normal run finds posts waiting, so it writes the first due one without planning again.
    monkeypatch.setattr(bluesky, "get_post_metrics", lambda uri: {"likes": 0, "reposts": 0, "replies": 0})
    code, llm, _ = go([], POST_SCRIPT)
    assert code == 0 and len(llm.calls) == 2 and len(bsky) == 1 and len(state().posts) == 3


def test_plan_only_is_refused_while_posts_are_waiting_and_costs_nothing(data, bsky):  # noqa: F811
    go([], PLAN_SCRIPT + POST_SCRIPT)
    before = state().model_dump()
    code, llm, _ = go(["--plan-only"], [])
    assert code == 2 and llm.calls == []
    assert state().model_dump() == before
    assert "plan now only runs when the queue is empty" in plan_only_summary()["outcomes"][0]["reason"]


def test_plan_only_counts_a_live_post_still_marked_planned_as_done(data, bsky, monkeypatch):  # noqa: F811
    go(["--plan-only"], PLAN_SCRIPT)
    for p in state().posts:  # every post went out, but the state file never heard (a crash after publishing)
        add_published(p.id, timedelta(hours=30))
    code, llm, _ = go(["--plan-only"], [week_json(("2026-10-24", "2026-10-26", "2026-10-28"))])
    assert code == 0 and len(llm.calls) == 1


def test_plan_only_dry_run_plans_but_saves_nothing(data, bsky):  # noqa: F811
    code, llm, _ = go(["--plan-only", "--dry-run"], PLAN_SCRIPT)
    assert code == 0 and len(llm.calls) == 1
    assert not plan_state.state_path().exists()


@pytest.mark.parametrize("extra", [["--measure-only"], ["--requeue", "post_x"]])
def test_plan_only_does_not_combine_with_other_modes(data, extra):  # noqa: F811
    code, llm, _ = go(["--plan-only", *extra], [])
    assert code == 2 and llm.calls == []
