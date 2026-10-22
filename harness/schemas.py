"""Data contracts shared by every module, taken from the build plan's pydantic sketches.

Every agent output is validated against one of these models before the harness acts on it.
The bounds in the plan's comments (3 to 7 posts, 300 characters, attempt 1 to 3, scores 1 to 5)
are enforced here so an out-of-range model answer fails validation and goes to the repair step.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

MAX_POST_CHARS = 300
MAX_ATTEMPTS = 3
CRITIQUE_DIMENSIONS = ("voice", "clarity", "cta", "policy_risk")

Score = Annotated[int, Field(ge=1, le=5)]


class PlannedPost(BaseModel):
    id: str = Field(min_length=1)
    day: date
    topic: str = Field(min_length=1)
    angle: str = Field(min_length=1)
    goal: Literal["awareness", "engagement", "click"]


class WeekPlan(BaseModel):
    """The "cite a learning when any exist" rule needs the learnings, so the planner step checks it, not this model."""

    week_of: date
    posts: list[PlannedPost] = Field(min_length=3, max_length=7)
    rationale: str = Field(min_length=1)


class Draft(BaseModel):
    """post_id and attempt are overwritten by the harness; the model only really supplies text."""

    post_id: str
    text: str = Field(min_length=1, max_length=MAX_POST_CHARS)
    attempt: int = Field(ge=1, le=MAX_ATTEMPTS)


class Critique(BaseModel):
    """`passed` defaults to False and is always recomputed by apply_threshold; whatever the model sends is ignored."""

    voice: Score
    clarity: Score
    cta: Score
    policy_risk: Score  # 5 is safest
    reasons: dict[str, str]
    passed: bool = False

    @field_validator("reasons")
    @classmethod
    def _one_reason_per_score(cls, reasons: dict[str, str]) -> dict[str, str]:
        """The rubric requires a reason per score; without them the writer gets no feedback to revise on."""
        missing = [d for d in CRITIQUE_DIMENSIONS if not reasons.get(d, "").strip()]
        if missing:
            raise ValueError(f"missing reasons for: {', '.join(missing)}")
        return reasons


class TraceEvent(BaseModel):
    ts: datetime
    run_id: str
    agent: Literal["planner", "writer", "critic", "analyst", "harness"]
    kind: Literal["llm_call", "tool_call", "guardrail", "decision"]
    summary_in: str
    summary_out: str
    ok: bool
    model: str | None = None
    latency_ms: int | None = None


class Learning(BaseModel):
    """run_id, post_id and metrics are set by the harness; the analyst only really supplies the insight."""

    run_id: str = Field(min_length=1)
    post_id: str = Field(min_length=1)
    metrics: dict[str, int]  # likes, reposts, replies
    insight: str = Field(min_length=1)  # one sentence the next planner run can use


class BrandBrief(BaseModel):
    """Not in the plan's contract block, but validating the brief matters: a brief missing
    banned_phrases would otherwise quietly turn the banned-phrase guardrail into a no-op."""

    name: str = Field(min_length=1)
    one_liner: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    voice: list[str] = Field(min_length=3, max_length=3)
    do: list[str]
    dont: list[str]
    banned_phrases: list[str]
    goal: str = Field(min_length=1)
    cta_url: str = Field(pattern=r"^https?://\S+$")


def passes_threshold(critique: Critique, min_score: int = 4) -> bool:
    """A single weak dimension fails the draft: averaging would let a risky post through on charm."""
    return all(getattr(critique, d) >= min_score for d in CRITIQUE_DIMENSIONS)


def apply_threshold(critique: Critique, min_score: int = 4) -> Critique:
    """Return the critique with `passed` overwritten by the harness verdict (architecture rule 5)."""
    return critique.model_copy(update={"passed": passes_threshold(critique, min_score)})
