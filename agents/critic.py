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
clarity: 5 = one idea, readable in 5 seconds, under {MAX_POST_CHARS} characters, and about the planned post's topic. 1 = vague, cluttered, two messages at once, or about something other than the planned topic.
cta: 5 = one specific next step that fits the post's goal. 1 = no action, or pushy and misleading.
policy_risk (5 = safest): 5 = no banned phrase, every factual claim is in the brief or the planned post, nothing sensitive. 3 = a claim that is not in the brief or the planned post. 1 = makes claims the business cannot back up."""

# The first live post invented "the starter smells like yogurt" and scored all 5s (ISSUES_LOG 7.4): the
# critic could not see the plan, and the brief's "do" list made the invented detail look like good voice.
FACT_CHECK = """Fact check: compare every factual claim in the draft with the brand_brief and planned_post data. A factual claim is anything about the product, process, ingredients, sensory properties (how something smells, tastes, looks or feels), results, prices, times, people, awards or comparisons. Any such claim that is not in the brief or the planned post means policy_risk of 3 or lower, and the policy_risk reason must quote the unsupported claim word for word. Sensory and craft details are factual claims too: the brief's "do" list asks for concrete detail, but that detail must still come from the brief or the planned post. Greetings, enthusiasm and invitations are not claims."""

# Run run_20261023_082541_ee5488: the topic was "Free sample loaf with every first class booking", the draft was
# about bulk-fermented dough, and it scored all 5s. Fact check and rubric never asked whether the post was on topic.
TOPIC_FIT = """Topic fit: the draft must be about the planned_post topic and use its angle. If the topic's main subject (for example an offer, a product or an event) is missing from the draft, or the draft is mainly about something else, even something true and well written from the brief, clarity is 2 or lower and the clarity reason must name the topic and say what the draft covers instead. A draft on the topic that skips the angle is a 3 or lower."""


def system_prompt(brief: BrandBrief) -> str:
    return f"""You are a strict reviewer of social posts for {brief.name}. You do not rewrite the post.

{RUBRIC}

Be strict and specific. Never give a score above 3 without a concrete reason that points at the text.
Any banned phrase, health claim, urgency pressure or promise the brief cannot back up means policy_risk of 2 or lower.
{FACT_CHECK}
{TOPIC_FIT}

{DATA_NOTE}

Reply with only a JSON object:
{{"voice": n, "clarity": n, "cta": n, "policy_risk": n,
  "reasons": {{"voice": "...", "clarity": "...", "cta": "...", "policy_risk": "..."}}}}"""


def user_prompt(draft: Draft, planned: PlannedPost, brief: BrandBrief) -> str:
    """The same planned_post block the writer gets, so the fact check judges against exactly the facts it had."""
    return "\n\n".join([
        data_block("brand_brief", brief.model_dump()),
        data_block("planned_post", planned.model_dump(mode="json")),
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
