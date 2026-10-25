"""Writer: turns one planned post (and, on a revision, the critic's reasons) into a Draft.

The brief is in the prompt because the plan's input contract says so, and get_brand_brief is also
offered (the writer's whole allowlist) so the tool path is real and traced. The model supplies only
the text; post_id and attempt are set by the harness.
"""

from __future__ import annotations

from agents.base import DATA_NOTE, ToolDispatcher, budget_for, data_block
from harness.llm import LLM
from harness.schemas import MAX_POST_CHARS, BrandBrief, Critique, Draft, PlannedPost

ROLE = "writer"
# Asked for below the hard cap: models overshoot (348 characters on the first live run), and Draft rejects 301+.
TARGET_CHARS = 280
# Run run_20261023_082541_ee5488: the topic was a free sample loaf offer, the draft was about bulk fermentation.
# The brief's goal and "do" list are all about class and craft detail, and nothing said the topic outranks them.
TOPIC_RULE = ("Write about the planned_post topic and use its angle. The brief says how to sound and what is "
              "allowed, not what to write about; if the topic is an offer, the offer must appear in the post.")
# Run run_20261023_090036_b0e71e: the draft opened with the topic pasted word for word, then added "Beginners often
# notice the crust and crumb first", a claim about customers that neither the brief nor the plan supports.
STYLE_RULE = ("Say the topic the way the bakery would say it aloud: do not open with its text word for word. Do not "
              "say what people usually do, notice or feel, because that is a claim about customers. Where it fits, "
              "mention one thing the brief names (crust, crumb, flour, the oven) without describing how it smells, "
              "tastes or feels beyond what the brief says.")
# Oct 25: four repairs asked for 280 and came back over the 300 cap (391, 303, 402 and 312 characters; runs 4ca574,
# 395daf, 8202cc and d77bec), so the one repair aims lower than the first draft to leave room for the overshoot.
REPAIR_TARGET_CHARS = 240
REPAIR_HINT = f"Keep the text to {REPAIR_TARGET_CHARS} characters or fewer."


def system_prompt(brief: BrandBrief) -> str:
    return f"""You write one Bluesky post for {brief.name}.

Rules:
- Sound {", ".join(brief.voice)}. Follow every item in the brief's "do" list.
- Never do anything in the brief's "dont" list.
- Never use any banned phrase, in any spelling or form: {"; ".join([*brief.banned_phrases, *brief.banned_variants])}.
- {TARGET_CHARS} characters or fewer, counting the link (the hard limit is {MAX_POST_CHARS}). One idea. End with one clear, low-pressure next step that fits the goal.
- Only state facts that are in the brief or the planned post's topic; the angle says what to focus on, not what is true.
- {TOPIC_RULE}
- {STYLE_RULE}

{DATA_NOTE}

You may call get_brand_brief if you need the brief again.
Reply with only a JSON object: {{"text": "<the post>"}}"""


def user_prompt(planned: PlannedPost, brief: BrandBrief, feedback: Critique | None, previous: Draft | None,
                min_score: int = 4) -> str:
    parts = [data_block("brand_brief", brief.model_dump()),
             data_block("planned_post", planned.model_dump(mode="json"))]
    if feedback is not None and previous is not None:
        parts.append(data_block("previous_draft", previous.text))
        parts.append(data_block("critic_reasons", {
            dim: {"score": getattr(feedback, dim), "reason": feedback.reasons.get(dim, "")}
            for dim in ("voice", "clarity", "cta", "policy_risk")}))
        parts.append(f"Revise the previous draft so every score can reach {min_score} or more. "
                     "Fix each reason above.")
    else:
        parts.append("Write the post.")
    return "\n\n".join(parts)


def write(llm: LLM, run_id: str, planned: PlannedPost, brief: BrandBrief, attempt: int,
          feedback: Critique | None = None, previous: Draft | None = None, min_score: int = 4) -> Draft:
    """One writer invocation: its own attempt budget, its own tool allowlist, one repair at most."""
    tools = ToolDispatcher(run_id, ROLE)
    messages = [{"role": "system", "content": system_prompt(brief)},
                {"role": "user", "content": user_prompt(planned, brief, feedback, previous, min_score)}]
    return llm.chat_json(run_id, ROLE, messages, Draft, tools=tools.specs(), run_tool=tools,
                         overrides={"post_id": planned.id, "attempt": attempt}, budget=budget_for(ROLE),
                         repair_hint=REPAIR_HINT)
