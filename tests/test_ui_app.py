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


def click(demo, label: str, *inputs):
    """Call the handler wired to the button with this label, the way a click would (no browser needed)."""
    button = next(b for b in demo.blocks.values() if isinstance(b, gr.Button) and b.value == label)
    fn = next(f for f in demo.fns.values() if any(t[0] == button._id for t in f.targets))
    return fn.fn(*inputs)


def recorder(calls: list[list[str]]):
    return lambda argv, input_fn, say: calls.append(argv) or 0


def test_a_live_run_needs_a_second_click():
    started: list[list[str]] = []
    ctl = Controller(runner=recorder(started))
    demo = app.build(ctl)
    click(demo, "Run next post", "")
    click(demo, "Cancel")
    assert started == [] and not ctl.busy()
    click(demo, "Yes, start the live run", "next", "", "", "engagement")
    ctl.shutdown(wait_s=5)
    assert started == [[]]  # no --dry-run: this is the live path


def test_a_live_topic_post_needs_a_topic_and_a_second_click():
    posts: list[list[str]] = []
    ctl = Controller(post_runner=recorder(posts))
    demo = app.build(ctl)
    shown, note, which, _ = click(demo, "Post this topic live", "  ")
    assert note == "Write a topic first." and shown["visible"] is False
    shown, note, which, text = click(demo, "Post this topic live", "Rye crust")
    assert shown["visible"] is True and which == "topic" and "live post on this topic" in text
    assert posts == []
    click(demo, "Yes, start the live run", which, "Rye crust", "", "click")
    ctl.shutdown(wait_s=5)
    assert posts == [["--topic", "Rye crust", "--goal", "click"]]
