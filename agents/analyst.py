"""Analyst: turns one post and its measured counts into a one-sentence learning for the next plan.

It is offered no tools. The harness fetched the metrics and puts them in the prompt, so the model has
nothing to look up and cannot ask for a different post. The model supplies only `insight`; run_id,
post_id and the metrics are set by the harness, so a model cannot attach a learning to the wrong post
or change the numbers it is explaining.
"""

from __future__ import annotations

from agents.base import DATA_NOTE, budget_for, data_block
from harness.llm import LLM, Budget
from harness.schemas import Learning

ROLE = "analyst"

SYSTEM = f"""You review how one social post performed and write one learning for the person who plans next week's posts.

Rules:
- One sentence that says what the numbers suggest about the post's topic, angle, goal or wording.
- Use only the post text and counts given. With counts this small, say what they suggest, not what they prove.
- Do not invent audience facts, reach or impressions: they are not given.

{DATA_NOTE}

Reply with only a JSON object: {{"insight": "<one sentence>"}}"""


def analyze(llm: LLM, run_id: str, post_id: str, text: str, metrics: dict[str, int],
            budget: Budget | None = None) -> Learning:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "\n\n".join([
                    data_block("post", text), data_block("metrics", metrics), "Write the learning."])}]
    return llm.chat_json(run_id, ROLE, messages, Learning,
                         overrides={"run_id": run_id, "post_id": post_id, "metrics": metrics},
                         budget=budget or budget_for(ROLE))
