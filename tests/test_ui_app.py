"""ui/app.py builds its page, stays on 127.0.0.1, exposes no API endpoints, and asks twice before any live run.
Skipped where gradio is not installed (CI installs only requirements.txt)."""

from __future__ import annotations

import os

import pytest

gr = pytest.importorskip("gradio")

from ui import app  # noqa: E402
from ui.controller import Controller  # noqa: E402


def test_the_page_builds_and_is_local_only():
    demo = app.build(Controller())
    assert demo.title == "Autopilot"
    assert app.HOST == "127.0.0.1"
    assert os.environ["GRADIO_ANALYTICS_ENABLED"] == "False"


def test_no_event_is_callable_through_the_gradio_api():
    """Start and Approve must come from the page, not from a script using Gradio's client."""
    demo = app.build(Controller())
    assert {f.api_visibility for f in demo.fns.values()} == {"private"}
    assert demo.get_api_info() == {"named_endpoints": {}, "unnamed_endpoints": {}}


def click(demo, elem_id: str, *inputs):
    """Call the handler wired to the button with this id, the way a click would (no browser needed)."""
    button = next(b for b in demo.blocks.values() if isinstance(b, gr.Button) and b.elem_id == elem_id)
    fn = next(f for f in demo.fns.values() if any(t[0] == button._id for t in f.targets))
    return fn.fn(*inputs)


def recorder(calls: list[list[str]]):
    return lambda argv, input_fn, say: calls.append(argv) or 0


def test_a_live_run_needs_a_second_click():
    started: list[list[str]] = []
    ctl = Controller(runner=recorder(started))
    demo = app.build(ctl)
    click(demo, "run-live", "")
    click(demo, "confirm-cancel")
    assert started == [] and not ctl.busy()
    click(demo, "confirm-yes", "next", "", "", "engagement")
    ctl.shutdown(wait_s=5)
    assert started == [[]]  # no --dry-run: this is the live path


def test_a_live_topic_post_needs_a_topic_and_a_second_click():
    posts: list[list[str]] = []
    ctl = Controller(post_runner=recorder(posts))
    demo = app.build(ctl)
    shown, note, which, _ = click(demo, "topic-live", "  ")
    assert note == "Write a topic first." and shown["visible"] is False
    shown, note, which, text = click(demo, "topic-live", "Rye crust")
    assert shown["visible"] is True and which == "topic" and "Rye crust" in text and "Bluesky" in text
    assert posts == []
    click(demo, "confirm-yes", which, "Rye crust", "", "click")
    ctl.shutdown(wait_s=5)
    assert posts == [["--topic", "Rye crust", "--goal", "click"]]


def test_the_approval_dialog_escapes_the_draft_and_shows_its_length_and_scores():
    from ui.controller import Approval, Snapshot

    prompt = "\n--- draft (27 chars) ---\n<b>Rye</b> & crust, at 9am.\n--- end ---\nPublish this post? [y/N] "
    log = "attempt 1: ...\n  scores voice=5 clarity=4 cta=3 policy_risk=5"
    s = Snapshot(running=True, what="next post", dry_run=False, log=log, approval=Approval(1, prompt, False),
                 exit_code=None)
    body = app._approval_body(s, "Bramblewick Bakehouse")
    assert "&lt;b&gt;Rye&lt;/b&gt; &amp; crust" in body and "<b>Rye</b>" not in body  # model text is never HTML
    assert "27 / 300" in body and "clarity <b>4</b>" in body
    assert "Live" in app._approval_head(s) and "Bluesky now" in app._approval_head(s)
