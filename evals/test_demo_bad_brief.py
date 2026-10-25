"""The demo promises that the planted bad brief causes a critic rejection and then a guardrail block: pin it."""

from __future__ import annotations

import json

import pytest

from harness.fileio import read_jsonl
from harness.schemas import BrandBrief
from scripts import demo_bad_brief, run_post


@pytest.fixture
def outcome(tmp_path):
    code, events = demo_bad_brief.run_demo(tmp_path)
    return code, events, tmp_path


def test_the_planted_brief_is_a_valid_brief_that_contradicts_itself():
    brief = BrandBrief.model_validate_json(demo_bad_brief.BRIEF.read_text(encoding="utf-8"))
    assert any("Results guaranteed" in rule for rule in brief.do)
    assert "results guaranteed" in brief.banned_variants  # what the brief asks for, its own banned list forbids


def test_the_first_draft_is_rejected_by_the_critic_and_sent_back_for_revision(outcome):
    _, events, _ = outcome
    assert any(e.agent == "harness" and e.kind == "decision" and not e.ok and "attempt 1" in e.summary_in
               and e.summary_out == "below threshold 4: revise" for e in events)


def test_the_second_draft_passes_the_critic_but_the_harness_blocks_it(outcome):
    code, events, _ = outcome
    assert code == run_post.EXIT_BLOCKED
    assert any(e.kind == "decision" and e.ok and "attempt 2" in e.summary_in and e.summary_out == "passed on attempt 2"
               for e in events)
    blocked = [e for e in events if e.kind == "guardrail" and not e.ok and e.summary_in.startswith("check_banned")]
    assert blocked and "results guaranteed" in blocked[0].summary_out


def test_nothing_is_published_and_no_human_is_asked(outcome):
    _, events, work = outcome
    assert not any(e.kind == "tool_call" and e.summary_in.startswith("publish_post") for e in events)
    assert not any(e.kind == "guardrail" and e.summary_in.startswith("require_approval") and e.ok for e in events)
    assert read_jsonl(work / "approved.jsonl")[0] == []
    calls = work / "calls.jsonl"
    assert not calls.exists() or not [r for r in read_jsonl(calls)[0] if r.get("tool") == "publish_post"]


def test_the_scripted_replies_are_what_the_demo_doc_quotes():
    replies = demo_bad_brief.script()
    assert json.loads(replies[0])["text"] == demo_bad_brief.PUSHY
    assert json.loads(replies[2])["text"] == demo_bad_brief.PROMISE
