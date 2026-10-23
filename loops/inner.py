"""Inner loop: write, critique, revise. At most 3 attempts, then a human decides (architecture rule 6).

The loop never publishes and never asks for approval: it only returns a draft that passed the
harness threshold, or the full history of a post that did not. The caller runs the guardrails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agents import critic, writer
from harness import trace
from harness.llm import LLM, LLMError
from harness.schemas import MAX_ATTEMPTS, BrandBrief, Critique, Draft, PlannedPost, passes_threshold

Status = Literal["passed", "escalated", "failed"]


@dataclass(frozen=True)
class Attempt:
    draft: Draft
    critique: Critique


@dataclass
class InnerResult:
    """`failed` means a model or chain error before any draft existed; `escalated` means drafts a human should see
    (3 below the threshold, or fewer when a model error cut the loop short; `error` then says why)."""

    status: Status
    post_id: str
    attempts: list[Attempt] = field(default_factory=list)
    error: str | None = None

    @property
    def final(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None


def run_inner(llm: LLM, run_id: str, planned: PlannedPost, brief: BrandBrief, *,
              max_attempts: int = MAX_ATTEMPTS, min_score: int = 4) -> InnerResult:
    if not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError(f"max_attempts must be 1 to {MAX_ATTEMPTS}")
    result = InnerResult(status="escalated", post_id=planned.id)
    previous: Attempt | None = None
    for n in range(1, max_attempts + 1):
        try:
            draft = writer.write(llm, run_id, planned, brief, n,
                                 feedback=previous.critique if previous else None,
                                 previous=previous.draft if previous else None, min_score=min_score)
            scored = critic.critique(llm, run_id, draft, planned, brief, min_score)
        except LLMError as e:
            result.error = f"{type(e).__name__}: {e}"
            # Rule 6: once a draft exists, a human reviews it. "failed" is only for a run with nothing to show.
            result.status = "escalated" if result.attempts else "failed"
            verdict = "escalate to human review after a model error" if result.attempts else "failed"
            trace.log_event(run_id, "harness", "decision", f"inner loop {planned.id} attempt {n}",
                            f"{verdict}: {result.error}", ok=False)
            return result
        previous = Attempt(draft, scored)
        result.attempts.append(previous)
        scores = ", ".join(f"{d}={getattr(scored, d)}" for d in ("voice", "clarity", "cta", "policy_risk"))
        # Recomputed from the scores here too: the loop never trusts a stored flag, even the harness's own.
        if passes_threshold(scored, min_score):
            trace.log_event(run_id, "harness", "decision", f"inner loop {planned.id} attempt {n} | {scores}",
                            f"passed on attempt {n}", ok=True)
            result.status = "passed"
            return result
        verdict = "revise" if n < max_attempts else "escalate to human review"
        trace.log_event(run_id, "harness", "decision", f"inner loop {planned.id} attempt {n} | {scores}",
                        f"below threshold {min_score}: {verdict}", ok=False)
    return result
