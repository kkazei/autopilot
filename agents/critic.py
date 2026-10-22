"""Critic: scores a draft on the plan's rubric. It has no tools and no say in whether the draft passes.

`passed` is never asked for; if the model sends it anyway it is overwritten by apply_threshold,
which looks only at the scores (architecture rule 5).
"""

from __future__ import annotations

from agents.base import DATA_NOTE, ToolDispatcher, budget_for, data_block
from harness.llm import LLM
from harness.schemas import MAX_POST_CHARS, BrandBrief, Critique, Draft, PlannedPost, apply_threshold

ROLE = "critic"

RUBRIC = f"""Score each dimension from 1 to 5 and give a one-sentence reason for each score.

voice: 5 = sounds like the brief's three voice words, nothing off-tone. 1 = generic, or breaks the "dont" list.
clarity: 5 = one idea, readable in 5 seconds, under {MAX_POST_CHARS} characters. 1 = vague, cluttered, or two messages at once.
cta: 5 = one specific next step that fits the post's goal. 1 = no action, or pushy and misleading.
policy_risk (5 = safest): 5 = no banned phrase, no unverifiable claim, nothing sensitive. 1 = makes claims the business cannot back up."""


def system_prompt(brief: BrandBrief) -> str:
    return f"""You are a strict reviewer of social posts for {brief.name}. You do not rewrite the post.

{RUBRIC}

Be strict and specific. Never give a score above 3 without a concrete reason that points at the text.
Any banned phrase, health claim, urgency pressure or promise the brief cannot back up means policy_risk of 2 or lower.

{DATA_NOTE}

Reply with only a JSON object:
{{"voice": n, "clarity": n, "cta": n, "policy_risk": n,
  "reasons": {{"voice": "...", "clarity": "...", "cta": "...", "policy_risk": "..."}}}}"""


def user_prompt(draft: Draft, planned: PlannedPost, brief: BrandBrief) -> str:
    return "\n\n".join([
        data_block("brand_brief", brief.model_dump()),
        data_block("post_goal", planned.goal),
        data_block("draft", draft.text),
        f"The draft is {len(draft.text)} characters. Score it.",
    ])


def critique(llm: LLM, run_id: str, draft: Draft, planned: PlannedPost, brief: BrandBrief,
             min_score: int = 4) -> Critique:
    """The model's scores are kept; its verdict is not. `passed` comes from the harness threshold."""
    tools = ToolDispatcher(run_id, ROLE)  # the critic's allowlist is empty, so no tools are offered
    messages = [{"role": "system", "content": system_prompt(brief)},
                {"role": "user", "content": user_prompt(draft, planned, brief)}]
    scored = llm.chat_json(run_id, ROLE, messages, Critique, tools=tools.specs(), run_tool=tools,
                           overrides={"passed": False}, budget=budget_for(ROLE))
    return apply_threshold(scored, min_score)
