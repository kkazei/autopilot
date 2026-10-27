"""ui/app.py builds its page and stays on 127.0.0.1. Skipped where gradio is not installed (CI installs only
requirements.txt)."""

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


def click(demo, label: str):
    """Call the handler wired to the button with this label, the way a click would (no browser needed)."""
    button = next(b for b in demo.blocks.values() if isinstance(b, gr.Button) and b.value == label)
    fn = next(f for f in demo.fns.values() if any(t[0] == button._id for t in f.targets))
    return fn.fn()


def test_a_live_run_needs_a_second_click():
    started: list[list[str]] = []
    ctl = Controller(runner=lambda argv, input_fn, say: started.append(argv) or 0)
    demo = app.build(ctl)
    click(demo, "Run next post")
    click(demo, "Cancel")
    assert started == [] and not ctl.busy()
    click(demo, "Yes, start the live run")
    ctl.shutdown(wait_s=5)
    assert started == [[]]  # no --dry-run: this is the live path
