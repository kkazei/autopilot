"""Planner: proposes a week of posts, using what earlier posts taught us. Read-only: it sees the brief and learnings.

The model's post ids are placeholders (the harness replaces them), and week_of is set by the harness. The harness
then checks two things the schema cannot: every post falls in the next seven days, and, when learnings exist,
the rationale cites at least one of them as [learning:<post_id>]. A citation only proves the model named a real
learning, not that the plan used it; that stays a judgement for a human reading the trace.
One retry explains what was wrong. It shares the planner's attempt budget, so a stubborn model cannot loop.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from agents.base import DATA_NOTE, ToolDispatcher, budget_for, data_block
from harness import trace
from harness.llm import LLM, Budget, LLMError
from harness.measure import NOT_ENOUGH_DATA_INSIGHT
from harness.schemas import BrandBrief, WeekPlan

ROLE = "planner"
PLAN_DAYS = 7
CITE_RE = re.compile(r"\[learning:([A-Za-z0-9_-]{1,64})\]")


class PlanRejected(LLMError):
    """The plan broke a harness rule even after one retry; the run fails cleanly instead of using it."""


def system_prompt(brief: BrandBrief) -> str:
    return f"""You plan the next week of Bluesky posts for {brief.name}.

Rules:
- Between 3 and 7 posts, at most one per day, each on a date from today to six days after today (YYYY-MM-DD).
- Each post: id (a placeholder such as "p1"), day, topic, angle (one concrete detail or technique) and goal
  (exactly one of "awareness", "engagement", "click").
- Plan only things that are in the brand brief: classes, bakes and techniques it names. Do not invent offers, prices or events.
- If learnings with data are given, use them, and cite each one you use in the rationale as [learning:<post_id>], copying its post_id exactly.
- A learning that says "Not enough data yet" carries no signal: do not draw conclusions from it.

{DATA_NOTE}

You may call get_brand_brief or get_learnings if you need them again.
Reply with only a JSON object:
{{"posts": [{{"id": "p1", "day": "YYYY-MM-DD", "topic": "...", "angle": "...", "goal": "click"}}], "rationale": "..."}}"""


def user_prompt(brief: BrandBrief, learnings: list[dict[str, Any]], today: date) -> str:
    return "\n\n".join([
        data_block("brand_brief", brief.model_dump()),
        data_block("learnings", learnings or "none yet"),
        f"Today is {today.isoformat()} (UTC). Plan the week.",
    ])


def check_plan(plan: WeekPlan, today: date, learnings: list[dict[str, Any]]) -> list[str]:
    """Problems with a schema-valid plan, worded so they can be shown to the model."""
    problems = []
    last = today + timedelta(days=PLAN_DAYS - 1)
    for p in plan.posts:
        if not today <= p.day <= last:
            problems.append(f"post {p.id!r} is dated {p.day}; every day must be from {today} to {last}")
    # Only a learning with signal can be cited: while every learning is "not enough data" (a young account),
    # demanding a citation would make the planner cite noise, or burn its one retry and fail the plan.
    valid = {str(r["post_id"]) for r in learnings if r.get("insight") != NOT_ENOUGH_DATA_INSIGHT}
    if valid and not valid & set(CITE_RE.findall(plan.rationale)):
        problems.append("the rationale must cite at least one learning as [learning:<post_id>] using a post_id "
                        f"from the learnings (valid ids: {', '.join(sorted(valid))})")
    return problems


def plan_week(llm: LLM, run_id: str, brief: BrandBrief, learnings: list[dict[str, Any]], today: date,
              budget: Budget | None = None) -> WeekPlan:
    """Raises LLMError (including PlanRejected) when no acceptable plan comes back; never returns an unchecked plan."""
    tools = ToolDispatcher(run_id, ROLE)
    budget = budget or budget_for(ROLE)
    messages = [{"role": "system", "content": system_prompt(brief)},
                {"role": "user", "content": user_prompt(brief, learnings, today)}]
    problems: list[str] = []
    for attempt in (1, 2):
        plan = llm.chat_json(run_id, ROLE, messages, WeekPlan, tools=tools.specs(), run_tool=tools,
                             overrides={"week_of": today}, budget=budget)
        problems = check_plan(plan, today, learnings)
        trace.log_event(run_id, "harness", "decision", f"check plan (attempt {attempt})",
                        "ok" if not problems else "; ".join(problems), ok=not problems)
        if not problems:
            return plan
        messages = [*messages, {"role": "assistant", "content": plan.model_dump_json()},
                    {"role": "user", "content": "That plan was rejected: " + "; ".join(problems)
                     + ". Reply with only the corrected JSON object."}]
    raise PlanRejected("plan rejected after one retry: " + "; ".join(problems))
