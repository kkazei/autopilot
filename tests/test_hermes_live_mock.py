"""The real Hermes binary against a scripted model: no network beyond loopback and no quota.

Skipped when `hermes` is not installed (CI). These are the tests that show the config, the MCP allowlist and the
cross-check work with the actual process, not only with the fake in test_hermes_runner.py.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date

import pytest

from agents import writer
from harness import trace
from harness.hermes_llm import HermesWriterLLM
from harness.hermes_runner import HERMES_ENV, TOOL_PREFIX
from harness.llm import LLMResponse, MockLLM
from harness.schemas import BrandBrief, PlannedPost
from tests.helpers import REPO_ROOT, data  # noqa: F401 - fixture

pytestmark = [pytest.mark.hermes,
              pytest.mark.skipif(not (os.environ.get(HERMES_ENV) or shutil.which("hermes")),
                                 reason="hermes is not installed")]

BRIEF = BrandBrief.model_validate_json((REPO_ROOT / "data" / "brand_brief.json").read_text(encoding="utf-8"))
PLANNED = PlannedPost(id="p1", day=date(2026, 10, 24), topic="Saturday class", angle="flour", goal="click")
GOOD = json.dumps({"text": "Saturday's class starts with flour on your hands. Save a seat at the link."})


def call(name: str, args: dict) -> dict:
    return {"id": "c1", "type": "function", "function": {"name": f"{TOOL_PREFIX}{name}", "arguments": json.dumps(args)}}


def test_the_writer_runs_through_real_hermes_and_the_real_role_server(data):
    direct = MockLLM([LLMResponse(model="m:free", content=None, tool_calls=[call("get_brand_brief", {})]), GOOD])
    llm = HermesWriterLLM(direct)
    run_id = trace.start_run()
    draft = writer.write(llm, run_id, PLANNED, BRIEF, attempt=1)
    assert draft.text == json.loads(GOOD)["text"] and (llm.invocations, llm.fallbacks) == (1, 0)
    events = trace.read_run(run_id)
    tool = next(e for e in events if e.kind == "tool_call")
    assert "get_brand_brief" in tool.summary_in and "receipt" in tool.summary_out and tool.ok
    assert "cross-check: passed" in next(e for e in events if e.summary_in.startswith("hermes writer invocation")).summary_out
    # the model was offered exactly the writer's allowlist, never the harness-only tools
    assert direct.tools_offered and all(t == [f"{TOOL_PREFIX}get_brand_brief"] for t in direct.tools_offered[:2])


def test_a_model_asking_for_publish_post_is_stopped_and_the_run_falls_back(data):
    bad = LLMResponse(model="m:free", content=None, tool_calls=[call("publish_post", {"text": "hi", "post_id": "x"})])
    direct = MockLLM([bad, bad, bad, GOOD, GOOD])
    llm = HermesWriterLLM(direct)
    run_id = trace.start_run()
    draft = writer.write(llm, run_id, PLANNED, BRIEF, attempt=1)
    assert draft.text and llm.fallbacks == 1  # the post still gets written, by the direct chain
    log = " | ".join(f"{e.summary_in} => {e.summary_out}" for e in trace.read_run(run_id) if e.kind == "decision")
    assert "tool_unauthorized" in log and "exit_failed" in log
    assert not [e for e in trace.read_run(run_id) if e.kind == "tool_call"]  # the server never ran publish_post
