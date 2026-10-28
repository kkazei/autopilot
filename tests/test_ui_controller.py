"""ui/controller.py: one run at a time, approval through buttons, the timeout that carries a post forward, and a
redacted, capped log. The last tests drive the real outer run through the controller against MockLLM."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import timedelta

import pytest

from harness import plan_state
from harness.llm import MockLLM
from scripts import run_outer
from tests.helpers import GOOD_TEXT, NOW, add_published, data, scores, week_json  # noqa: F401
from tests.test_outer_loop import bsky  # noqa: F401
from ui import controller
from ui.controller import Controller, Snapshot


def wait_for(ctl: Controller, cond: Callable[[Snapshot], bool], timeout_s: float = 10.0) -> Snapshot:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        s = ctl.snapshot()
        if cond(s):
            return s
        time.sleep(0.01)
    raise AssertionError(f"condition not met; last snapshot: {ctl.snapshot()}")


def done(s: Snapshot) -> bool:
    return not s.running and (s.exit_code is not None or "crashed" in s.log)


def asking_runner(answers: list[str | BaseException]) -> Callable:
    """Asks for approval once and records what came back (an answer or the exception)."""
    def runner(argv, input_fn, say):
        say(f"argv={argv}")
        try:
            answers.append(input_fn("\n--- draft (5 chars) ---\nHello\n--- end ---\nPublish this post? [y/N] "))
        except EOFError as e:
            answers.append(e)
        return 0
    return runner


def test_one_run_at_a_time():
    release = threading.Event()
    ctl = Controller(runner=lambda argv, input_fn, say: release.wait(5) and 0)
    assert ctl.start(dry_run=True) == "Dry run started."
    assert "already going" in ctl.start(dry_run=False)
    assert ctl.busy()
    release.set()
    s = wait_for(ctl, done)
    assert s.exit_code == 0 and s.dry_run


@pytest.mark.parametrize(("choice", "expected"), [("approve", "y"), ("reject", "n")])
def test_the_buttons_answer_the_approval_prompt(choice, expected):
    answers: list = []
    ctl = Controller(runner=asking_runner(answers))
    ctl.start(dry_run=False)
    s = wait_for(ctl, lambda s: s.approval is not None)
    assert "Hello" in s.approval.prompt and not s.approval.dry_run
    ctl.answer(s.approval.id, choice)
    s = wait_for(ctl, done)
    assert answers == [expected]
    assert s.approval is None and "argv=[]" in s.log and "exit code 0" in s.log


def test_a_stale_or_second_answer_does_nothing():
    answers: list = []
    ctl = Controller(runner=asking_runner(answers))
    ctl.start(dry_run=True)
    s = wait_for(ctl, lambda s: s.approval is not None)
    assert "no longer waiting" in ctl.answer(s.approval.id + 1, "approve")  # a page left open from an older draft
    assert ctl.answer(s.approval.id, "reject").startswith("Rejected")
    assert "no longer waiting" in ctl.answer(s.approval.id, "approve")  # a double tap cannot flip the answer
    wait_for(ctl, done)
    assert answers == ["n"]
    assert "no longer waiting" in ctl.answer(s.approval.id, "approve")


def test_silence_raises_eof_so_the_harness_reads_no_approval_input():
    answers: list = []
    ctl = Controller(runner=asking_runner(answers), approval_timeout_s=0.05)
    ctl.start(dry_run=False)
    s = wait_for(ctl, done)
    assert len(answers) == 1 and isinstance(answers[0], EOFError)
    assert "carried forward" in s.log and s.approval is None


def test_not_now_raises_eof_at_once_without_claiming_a_timeout():
    answers: list = []
    ctl = Controller(runner=asking_runner(answers))
    ctl.start(dry_run=False)
    s = wait_for(ctl, lambda s: s.approval is not None)
    assert ctl.answer(s.approval.id, "not_now").startswith("Not now")
    s = wait_for(ctl, done)
    assert isinstance(answers[0], EOFError) and "no answer within" not in s.log


def test_shutdown_releases_a_pending_approval_so_the_run_ends():
    answers: list = []
    ctl = Controller(runner=asking_runner(answers))
    ctl.start(dry_run=False)
    wait_for(ctl, lambda s: s.approval is not None)
    ctl.shutdown(wait_s=5)
    assert not ctl.busy()
    assert isinstance(answers[0], EOFError)


def test_the_log_is_redacted_and_capped(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key-123456")
    ctl = Controller(log_limit=3)
    for i in range(5):
        ctl.say(f"line {i} key=not-a-real-key-123456")
    log = ctl.snapshot().log
    assert "not-a-real-key" not in log and "[REDACTED:OPENROUTER_API_KEY]" in log
    assert log.splitlines()[0].startswith("line 2")


def test_a_crashed_run_is_reported_and_the_app_can_start_another():
    def boom(argv, input_fn, say):
        raise RuntimeError("bad")

    ctl = Controller(runner=boom)
    ctl.start(dry_run=True)
    s = wait_for(ctl, done)
    assert "crashed (RuntimeError: bad)" in s.log and s.exit_code is None
    assert ctl.start(dry_run=True) == "Dry run started."
    wait_for(ctl, done)


def test_requeue_waits_for_a_running_run():
    release = threading.Event()
    calls: list[str] = []
    ctl = Controller(runner=lambda argv, input_fn, say: release.wait(5) and 0,
                     requeuer=lambda post_id, say: calls.append(post_id) or say(f"{post_id} queued") or 0)
    ctl.start(dry_run=True)
    assert "after it finishes" in ctl.requeue("post_1")
    release.set()
    wait_for(ctl, done)
    assert ctl.requeue("post_1") == "post_1 queued" and calls == ["post_1"]


def real_runner(script: list[str]) -> Callable:
    """The real scripts.run_outer.main, with only the model and the clock replaced, as the terminal tests do."""
    def runner(argv, input_fn, say):
        return run_outer.main(argv, llm=MockLLM(list(script)), input_fn=input_fn, now=NOW, env_file=None, say=say)
    return runner


def test_a_live_run_through_the_app_publishes_after_approve(data, bsky):  # noqa: F811
    ctl = Controller(runner=real_runner([week_json(), GOOD_TEXT, scores(5)]))
    ctl.start(dry_run=False)
    s = wait_for(ctl, lambda s: s.approval is not None)
    assert "Saturday's class" in s.approval.prompt
    assert bsky == []  # nothing goes out before the button
    ctl.answer(s.approval.id, "approve")
    s = wait_for(ctl, done)
    assert s.exit_code == 0 and len(bsky) == 1
    assert "published: at://" in s.log and "trace:" in s.log
    assert [p.status for p in plan_state.load_state().posts][0] == "published"


def test_no_answer_through_the_app_carries_the_post_forward_and_posts_nothing(data, bsky):  # noqa: F811
    ctl = Controller(runner=real_runner([week_json(), GOOD_TEXT, scores(5)]), approval_timeout_s=0.05)
    ctl.start(dry_run=False)
    s = wait_for(ctl, done)
    assert bsky == [] and s.exit_code == 5
    assert plan_state.load_state().posts[0].status == "carried_forward"
    assert "no approval input" in s.log


def test_status_texts_read_quota_rate_cap_and_plan(data):  # noqa: F811
    assert "0 of 45 model requests" in controller.quota_text(NOW)
    assert controller.rate_text(NOW).startswith("A post can go out now")
    add_published("post_a", age=timedelta(minutes=10))
    assert "minimum gap is 60" in controller.rate_text(NOW)
    rationale, rows, ids = controller.plan_rows()
    assert "No plan yet" in rationale and rows == [] and ids == []


def test_not_now_through_the_app_carries_the_post_forward_and_posts_nothing(data, bsky):  # noqa: F811
    ctl = Controller(runner=real_runner([week_json(), GOOD_TEXT, scores(5)]))
    ctl.start(dry_run=False)
    s = wait_for(ctl, lambda s: s.approval is not None)
    ctl.answer(s.approval.id, "not_now")
    s = wait_for(ctl, done)
    assert bsky == [] and plan_state.load_state().posts[0].status == "carried_forward"


def test_the_budget_line_shows_requests_left_and_warns_when_low(data, monkeypatch):  # noqa: F811
    line = controller.budget_line(NOW)
    assert "0 / 45" in line and "next run may make 16" in line and "posting: OK now" in line
    assert "Few requests left" not in line
    monkeypatch.setattr(controller.quota, "run_cap", lambda now: (4, 41, 0))
    line = controller.budget_line(NOW)
    assert "41 / 45" in line and "next run may make 4" in line and "Few requests left" in line


def recording_runner(calls: list[list[str]]) -> Callable:
    return lambda argv, input_fn, say: calls.append(argv) or 0


def test_topic_posts_and_plan_now_build_the_terminal_flags():
    outer, post = [], []
    ctl = Controller(runner=recording_runner(outer), post_runner=recording_runner(post))
    assert ctl.start_topic("  ", "", "click", dry_run=True) == "Write a topic first."
    ctl.start_topic(" Rye crust ", " ", "click", dry_run=True)
    s = wait_for(ctl, done)
    assert s.what == "topic post" and s.dry_run
    ctl.start_topic("Rye crust", "the crackle as it cools", "engagement", dry_run=False)
    wait_for(ctl, lambda s: done(s) and len(post) == 2)
    ctl.plan_now()
    s = wait_for(ctl, lambda s: done(s) and len(outer) == 1)
    assert post == [["--topic", "Rye crust", "--goal", "click", "--dry-run"],
                    ["--topic", "Rye crust", "--goal", "engagement", "--angle", "the crackle as it cools"]]
    assert outer == [["--plan-only"]] and s.what == "plan now" and not s.dry_run


def test_only_one_run_of_any_kind_at_a_time():
    release = threading.Event()
    ctl = Controller(runner=lambda argv, input_fn, say: release.wait(5) and 0)
    ctl.start(dry_run=True)
    assert "already going" in ctl.start_topic("Rye", "", "click", dry_run=True)
    assert "already going" in ctl.plan_now()
    release.set()
    wait_for(ctl, done)


def test_a_topic_dry_run_through_the_app_asks_then_publishes_a_dryrun_uri(data, bsky):  # noqa: F811
    from scripts import run_post

    def post_runner(argv, input_fn, say):
        return run_post.main(argv, llm=MockLLM([GOOD_TEXT, scores(5)]), input_fn=input_fn, now=NOW,
                             env_file=None, say=say)

    ctl = Controller(post_runner=post_runner)
    ctl.start_topic("Saturday class", "", "click", dry_run=True)
    s = wait_for(ctl, lambda s: s.approval is not None)
    assert s.approval.dry_run and "Saturday's class" in s.approval.prompt
    ctl.answer(s.approval.id, "approve")
    s = wait_for(ctl, done)
    assert s.exit_code == 0 and "published: dryrun://" in s.log and bsky == []


def test_topic_choices_are_the_planned_topics_newest_first_without_repeats(data):  # noqa: F811
    assert controller.topic_choices() == []
    posts = [plan_state.PostRecord(id=f"post_{i}", plan_id="plan_x", day=day, topic=topic, angle="a", goal="click")
             for i, (day, topic) in enumerate([("2026-10-23", "topic 3 "), ("2026-10-25", "Topic 2"),
                                               ("2026-10-27", "Topic 3")])]
    plan_state.save_state(plan_state.PlanState(posts=posts))  # the oldest repeats the newest in other case and spacing
    assert controller.topic_choices() == ["Topic 3", "Topic 2"]


def test_a_topic_left_empty_in_the_dropdown_is_refused():
    ctl = Controller(post_runner=lambda argv, input_fn, say: pytest.fail("must not start"))
    assert ctl.start_topic(None, None, "click", dry_run=True) == "Write a topic first."
