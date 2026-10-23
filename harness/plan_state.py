"""The weekly plan as the outer loop sees it: which posts are waiting, which are done and why the rest stopped.

One JSON file, written atomically under a lock. Every status change appends to the post's history, so the file
alone explains what happened to each post. The harness assigns post ids (the model's are placeholders), and
refuses to read a corrupt file rather than reset it: resetting would forget which posts already went out.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Collection, Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from harness import trace
from harness.fileio import atomic_write_text, file_lock
from harness.schemas import PlannedPost, WeekPlan

PLAN_STATE_FILE = "plan_state.json"
SCHEMA_VERSION = 1
MAX_RUNS_PER_POST = 2  # runs that ended before any draft existed, before the post is marked failed
MAX_ID_TRIES = 10

Status = Literal["planned", "carried_forward", "published", "blocked", "escalated", "failed"]
ACTIVE: tuple[Status, ...] = ("planned", "carried_forward")


class PlanStateError(RuntimeError):
    """The file is unreadable or invalid; nothing is rewritten, so a person can look at it first."""


class HistoryEntry(BaseModel):
    run_id: str
    status: Status
    at: datetime
    reason: str


class PostRecord(BaseModel):
    id: str
    plan_id: str
    day: date
    topic: str
    angle: str
    goal: Literal["awareness", "engagement", "click"]
    status: Status = "planned"
    runs_failed: int = 0
    uri: str | None = None
    history: list[HistoryEntry] = Field(default_factory=list)

    def planned_post(self) -> PlannedPost:
        return PlannedPost(id=self.id, day=self.day, topic=self.topic, angle=self.angle, goal=self.goal)


class PlanRecord(BaseModel):
    plan_id: str
    run_id: str
    week_of: date
    rationale: str
    created_at: datetime


class PlanState(BaseModel):
    schema_version: int = SCHEMA_VERSION
    plans: list[PlanRecord] = Field(default_factory=list)
    posts: list[PostRecord] = Field(default_factory=list)

    def post(self, post_id: str) -> PostRecord | None:
        return next((p for p in self.posts if p.id == post_id), None)

    def has_active(self) -> bool:
        return any(p.status in ACTIVE for p in self.posts)


def state_path() -> Path:
    return trace.data_dir() / PLAN_STATE_FILE


def load_state() -> PlanState:
    path = state_path()
    with file_lock(path):
        if not path.exists():
            return PlanState()
        try:
            state = PlanState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as e:
            raise PlanStateError(f"{path.name} is unreadable or invalid ({type(e).__name__})") from None
    if state.schema_version != SCHEMA_VERSION:
        raise PlanStateError(f"{path.name} has schema_version {state.schema_version}; expected {SCHEMA_VERSION}")
    return state


def save_state(state: PlanState) -> None:
    path = state_path()
    with file_lock(path):
        atomic_write_text(path, json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")


def new_post_id(taken: Collection[str]) -> str:
    """post_<hex8>, regenerated on a clash with a known id; a bounded loop, so a broken RNG cannot spin forever."""
    for _ in range(MAX_ID_TRIES):
        candidate = f"post_{secrets.token_hex(4)}"
        if candidate not in taken:
            return candidate
    raise PlanStateError("could not generate an unused post id")


def add_plan(state: PlanState, plan: WeekPlan, run_id: str, now: datetime, taken_ids: Collection[str]) -> list[PostRecord]:
    """Append a validated plan, replacing every model-supplied post id with a harness id."""
    plan_id = f"plan_{secrets.token_hex(4)}"
    taken = {*taken_ids, *(p.id for p in state.posts)}
    state.plans.append(PlanRecord(plan_id=plan_id, run_id=run_id, week_of=plan.week_of,
                                  rationale=plan.rationale, created_at=now))
    added = []
    for p in plan.posts:
        post_id = new_post_id(taken)
        taken.add(post_id)
        record = PostRecord(id=post_id, plan_id=plan_id, day=p.day, topic=p.topic, angle=p.angle, goal=p.goal,
                            history=[HistoryEntry(run_id=run_id, status="planned", at=now, reason="planned")])
        state.posts.append(record)
        added.append(record)
    return added


def mark(state: PlanState, post_id: str, status: Status, run_id: str, now: datetime, reason: str,
         uri: str | None = None) -> PostRecord:
    post = state.post(post_id)
    if post is None:
        raise PlanStateError(f"unknown post {post_id}")
    post.status = status
    if uri is not None:
        post.uri = uri
    post.history.append(HistoryEntry(run_id=run_id, status=status, at=now, reason=reason))
    return post


def record_failed_run(state: PlanState, post_id: str, run_id: str, now: datetime, reason: str) -> PostRecord:
    """A run that ended before any draft existed: retry next run, unless this was already the last allowed one."""
    post = state.post(post_id)
    if post is None:
        raise PlanStateError(f"unknown post {post_id}")
    post.runs_failed += 1
    if post.runs_failed >= MAX_RUNS_PER_POST:
        return mark(state, post_id, "failed", run_id, now, f"{reason}; failed in {post.runs_failed} runs")
    return mark(state, post_id, "carried_forward", run_id, now, reason)


def reconcile(state: PlanState, approved_rows: Iterable[Mapping[str, Any]], run_id: str, now: datetime) -> list[PostRecord]:
    """Settle active posts that approved.jsonl already holds, so a lost status write cannot send a post twice.

    publish() writes approved.jsonl before the plan state is saved, so a crash or failed write in between
    leaves a live post looking "planned" here. A pending row means the outcome is unknown: the post may be
    live, so it is settled as failed (for a person to check), never written again.
    """
    rows = {str(r.get("post_id")): r for r in approved_rows}
    settled = []
    for post in state.posts:
        row = rows.get(post.id)
        if row is None or post.status not in ACTIVE:
            continue
        if row.get("status", "published") == "pending":
            settled.append(mark(state, post.id, "failed", run_id, now,
                                "approved.jsonl has a pending row: publish outcome unknown, check the account"))
        else:
            settled.append(mark(state, post.id, "published", run_id, now,
                                "found in approved.jsonl (its status had not been saved)", uri=row.get("uri")))
    return settled


def select_due(state: PlanState, today: date, run_id: str, now: datetime) -> PostRecord | None:
    """The oldest due post. Any planned post whose day has passed becomes carried_forward on the way."""
    due = sorted((p for p in state.posts if p.status in ACTIVE and p.day <= today), key=lambda p: p.day)
    for p in due:
        if p.status == "planned" and p.day < today:
            mark(state, p.id, "carried_forward", run_id, now, f"day {p.day} passed")
    return due[0] if due else None


def requeue(state: PlanState, post_id: str, run_id: str, now: datetime) -> PostRecord:
    """Only an escalated post can be requeued, and only by a person: the same draft loop would likely fail the same way."""
    post = state.post(post_id)
    if post is None:
        raise PlanStateError(f"unknown post {post_id}")
    if post.status != "escalated":
        raise PlanStateError(f"{post_id} is {post.status}; only escalated posts can be requeued")
    post.runs_failed = 0
    return mark(state, post_id, "carried_forward", run_id, now, "requeued by a person")
