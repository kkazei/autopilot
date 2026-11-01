"""Planner: proposes a week of posts, using what earlier posts taught us. Read-only: it sees the brief and learnings.

The model's post ids are placeholders (the harness replaces them), and week_of is set by the harness. The harness
then checks two things the schema cannot: every post falls in the next seven days, and, when learnings exist,
the rationale names at least one of them by post id (asked for as [learning:<post_id>]). A citation only proves the model named a real
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
PLANNER_MAX_TOKENS = 8192  # a plan is ~1,000 tokens; two reasoning models ran out at 4,096 while thinking (Nov 1)


def cited_ids(text: str, valid: set[str]) -> set[str]:
    """The valid ids that stand alone in the text, whatever punctuation is around them. The prompt asks for
    [learning:<post_id>], but three plans on Nov 1 used real learnings and wrote them three other ways, last as a
    bare "post_365bd515 shows..." (run_20261101_130846_97517e). The check exists to prove the plan names a real
    learning, and a post id is random, so the id itself is the proof."""
    return {v for v in valid if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(v)}(?![A-Za-z0-9_-])", text)}


# Run run_20261024_114318_baec64: the angle "crust that cracks like leather" was invented, and because the writer
# and critic treated the planned post as fact, the claim passed the fact check. An angle now only names a focus.
ANGLE_RULE = ("The angle names one thing the brief mentions to focus on, using the brief's own words (for example "
              "\"the crust\" or \"the smell of the oven\"). It does not describe how anything looks, smells, tastes, "
              "feels or sounds, and makes no claim the brief does not make.")
# Run run_20261101_121726_340650: the prompt alone did not hold. The angle "the crust cracking as it cools" was planned
# anyway, and the critic rightly failed every draft that said so, because an angle is not a source of facts. So the
# harness now checks it: every content word of an angle must appear in the brief's positive fields. The "dont" list
# and banned phrases are left out, so "results" or "health" cannot ground an angle.
ANGLE_STOPWORDS = frozenset(
    "a an the and or of in on at to for with by from as is are be it its our your their this that these those "
    "one each every how what when why who we you they".split())
WORD_RE = re.compile(r"[a-z]+")


def _stem(word: str) -> str:
    """Crude on purpose: enough that "baking", "bakes" and "bake" match, without a stemming dependency."""
    for suffix in ("ing", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    return word.rstrip("es") if len(word) > 3 else word


MIN_PART_LEN = 4  # "dough" inside "sourdough" counts; "on" inside "one" does not


def brief_vocabulary(brief: BrandBrief) -> frozenset[str]:
    text = " ".join([brief.name, brief.one_liner, brief.audience, brief.goal, *brief.do, *brief.voice])
    return frozenset(_stem(w) for w in WORD_RE.findall(text.lower()))


def _grounded(word: str, vocabulary: frozenset[str]) -> bool:
    """A word of the brief, or the end of a longer one: run_20261101_124736_a2bae1 rejected "dough" at a sourdough
    bakery. Only the end, so a compound's head ("sourdough" grounds "dough", not "sour") is what counts."""
    stem = _stem(word)
    return stem in vocabulary or (len(word) >= MIN_PART_LEN and any(v.endswith(stem) and v != stem for v in vocabulary))


def ungrounded_words(angle: str, vocabulary: frozenset[str]) -> list[str]:
    words = [w for w in WORD_RE.findall(angle.lower()) if len(w) > 1 and w not in ANGLE_STOPWORDS]  # drops the "s" of "beginner's"
    return [w for w in words if not _grounded(w, vocabulary)]


# Run run_20261101_124736_a2bae1: told only what was wrong, the model fixed every angle but rewrote the rationale
# as an account of its fixes, which dropped the learning citations, so the corrected plan failed the other rule.
RETRY_NOTE = ("Change only what is listed above and keep everything else as it was, including the "
              "[learning:<post_id>] citations in the rationale. Reply with only the corrected JSON object.")


class PlanRejected(LLMError):
    """The plan broke a harness rule even after one retry; the run fails cleanly instead of using it."""


def system_prompt(brief: BrandBrief) -> str:
    return f"""You plan the next week of Bluesky posts for {brief.name}.

Rules:
- Between 3 and 7 posts, at most one per day, each on a date from today to six days after today (YYYY-MM-DD).
- Each post: id (a placeholder such as "p1"), day, topic, angle (one concrete detail or technique) and goal
  (exactly one of "awareness", "engagement", "click").
- {ANGLE_RULE}
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


def check_plan(plan: WeekPlan, today: date, learnings: list[dict[str, Any]], brief: BrandBrief) -> list[str]:
    """Problems with a schema-valid plan, worded so they can be shown to the model."""
    problems = []
    vocabulary = brief_vocabulary(brief)
    for p in plan.posts:
        if loose := ungrounded_words(p.angle, vocabulary):
            problems.append(f"post {p.id!r} has the angle {p.angle!r}, but {', '.join(map(repr, loose))} is not in "
                            "the brand brief; name a focus using the brief's own words")
    last = today + timedelta(days=PLAN_DAYS - 1)
    for p in plan.posts:
        if not today <= p.day <= last:
            problems.append(f"post {p.id!r} is dated {p.day}; every day must be from {today} to {last}")
    # Only a learning with signal can be cited: while every learning is "not enough data" (a young account),
    # demanding a citation would make the planner cite noise, or burn its one retry and fail the plan.
    valid = {str(r["post_id"]) for r in learnings if r.get("insight") != NOT_ENOUGH_DATA_INSIGHT}
    if valid and not cited_ids(plan.rationale, valid):
        example = sorted(valid)[0]
        problems.append("the rationale must cite at least one learning as [learning:<post_id>] using a post_id "
                        f"from the learnings (valid ids: {', '.join(sorted(valid))}); write it exactly like "
                        f"[learning:{example}], with the square brackets around the whole citation")
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
                             overrides={"week_of": today}, budget=budget, max_tokens=PLANNER_MAX_TOKENS)
        problems = check_plan(plan, today, learnings, brief)
        trace.log_event(run_id, "harness", "decision", f"check plan (attempt {attempt})",
                        "ok" if not problems else "; ".join(problems), ok=not problems)
        if not problems:
            return plan
        messages = [*messages, {"role": "assistant", "content": plan.model_dump_json()},
                    {"role": "user", "content": "That plan was rejected: " + "; ".join(problems) + ". " + RETRY_NOTE}]
    raise PlanRejected("plan rejected after one retry: " + "; ".join(problems))
