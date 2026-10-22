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


def system_prompt(brief: BrandBrief) -> str:
    return f"""You write one Bluesky post for {brief.name}.

Rules:
- Sound {", ".join(brief.voice)}. Follow every item in the brief's "do" list.
- Never do anything in the brief's "dont" list.
- Never use any banned phrase, in any spelling or form: {"; ".join(brief.banned_phrases)}.
- At most {MAX_POST_CHARS} characters. One idea. End with one clear, low-pressure next step that fits the goal.
- Only state facts that are in the brief or the planned post.

{DATA_NOTE}

You may call get_brand_brief if you need the brief again.
Reply with only a JSON object: {{"text": "<the post>"}}"""


def user_prompt(planned: PlannedPost, brief: BrandBrief, feedback: Critique | None, previous: Draft | None) -> str:
    parts = [data_block("brand_brief", brief.model_dump()),
             data_block("planned_post", planned.model_dump(mode="json"))]
    if feedback is not None and previous is not None:
        parts.append(data_block("previous_draft", previous.text))
        parts.append(data_block("critic_reasons", {
            dim: {"score": getattr(feedback, dim), "reason": feedback.reasons.get(dim, "")}
            for dim in ("voice", "clarity", "cta", "policy_risk")}))
        parts.append("Revise the previous draft so every score can reach 4 or more. Fix each reason above.")
    else:
        parts.append("Write the post.")
    return "\n\n".join(parts)


def write(llm: LLM, run_id: str, planned: PlannedPost, brief: BrandBrief, attempt: int,
          feedback: Critique | None = None, previous: Draft | None = None) -> Draft:
    """One writer invocation: its own attempt budget, its own tool allowlist, one repair at most."""
    tools = ToolDispatcher(run_id, ROLE)
    messages = [{"role": "system", "content": system_prompt(brief)},
                {"role": "user", "content": user_prompt(planned, brief, feedback, previous)}]
    return llm.chat_json(run_id, ROLE, messages, Draft, tools=tools.specs(), run_tool=tools,
                         overrides={"post_id": planned.id, "attempt": attempt}, budget=budget_for(ROLE))
