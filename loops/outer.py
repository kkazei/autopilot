"""Outer loop: measure old posts, pick the next due post (planning a new week only when none are left), then run
the inner loop and publish it. One post per run, so the schedule decides the pace and the free quota is spread out.

The orchestrator owns all control flow (architecture rule 1): the planner and analyst return data and decide nothing.
Every request an agent makes is charged to one run-wide budget, and the run holds a lock that outlasts the
human approval prompt, so a second run cannot start mid-way and double-post.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import run_budget
from agents.planner import plan_week
from harness import guardrails, plan_state, quota, trace
from harness.fileio import LockTimeout, file_lock
from harness.llm import LLM, Budget, LLMError
from harness.measure import measure_posts
from harness.plan_state import PlanState, PlanStateError, PostRecord
from harness.publish import (
    ApprovedLogError,
    Clock,
    PublishBlocked,
    PublishRefused,
    fetch_learnings,
    live_records,
    publish,
    utc_now,
)
from harness.schemas import BrandBrief
from loops.inner import InnerResult, run_inner
from mcp_server.server import ToolRefused

EXIT_OK, EXIT_REFUSED, EXIT_ESCALATED, EXIT_FAILED, EXIT_BLOCKED, EXIT_BUSY = 0, 2, 3, 4, 5, 6
OUTER_LOCK_FILE = "outer_run"
# Longer than any real run, including a person sitting at the approval prompt. A crash leaves the lock behind,
# and this is how long that blocks the next run (the refusal message says how to clear it sooner).
OUTER_LOCK_STALE_S = 6 * 60 * 60.0
# An approval answer that means "nobody was there", not "a person said no": the post waits instead of being blocked.
_NO_ONE_THERE = "no approval input"
SUMMARY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class OuterOptions:
    dry_run: bool = False
    approve: bool = True
    measure_only: bool = False
    min_score: int = 4


@dataclass
class RunReport:
    """What the run-summary event records. Filled in as the run goes, so a run that stops early still says why."""

    plan: dict[str, Any] | None = None  # the plan made by this run, if any
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    learnings: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def outcome(self, post_id: str | None, status: str, reason: str, **extra: Any) -> None:
        self.outcomes.append({"post_id": post_id, "status": status, "reason": reason, **extra})


def _lock_path() -> Path:
    return trace.data_dir() / f"{OUTER_LOCK_FILE}.lock"


def _acquire(stack: contextlib.ExitStack, say: Callable[[str], None]) -> bool:
    """Take the outer lock, or say why not. Only this call's LockTimeout means 'busy'; later ones are real errors."""
    try:
        stack.enter_context(file_lock(trace.data_dir() / OUTER_LOCK_FILE, timeout_s=0, stale_s=OUTER_LOCK_STALE_S))
    except LockTimeout:
        say(f"refused: another outer run is active. If a crash left the lock behind, confirm no run is active, "
            f"then delete {_lock_path()} (it clears itself after {OUTER_LOCK_STALE_S / 3600:g} hours).")
        return False
    return True


def requeue_post(post_id: str, say: Callable[[str], None] = print, clock: Clock = utc_now) -> int:
    """A person puts an escalated post back in the queue. No model calls."""
    with contextlib.ExitStack() as stack:
        if not _acquire(stack, say):
            return EXIT_BUSY
        run_id = trace.start_run()
        try:
            state = plan_state.load_state()
            plan_state.requeue(state, post_id, run_id, clock())
            plan_state.save_state(state)
        except (PlanStateError, OSError, LockTimeout) as e:
            trace.log_event(run_id, "harness", "decision", f"requeue {post_id}", f"refused: {e}", ok=False)
            say(f"refused: {e}")
            return EXIT_REFUSED
        trace.log_event(run_id, "harness", "decision", f"requeue {post_id}", "carried_forward", ok=True)
        say(f"{post_id} is queued again (carried_forward)")
        return EXIT_OK


def run_outer(llm: LLM, brief: BrandBrief, opts: OuterOptions, *, input_fn: Callable[[str], str] = input,
              clock: Clock = utc_now, say: Callable[[str], None] = print) -> int:
    # Enforced here, not only in the CLI: publish() takes the caller's word that a human approved, so any other
    # caller (a cron wrapper, a test) must not be able to reach a live post with approval off.
    if not opts.approve and not opts.dry_run:
        say("refused: approval can only be off for a dry run")
        return EXIT_REFUSED
    with contextlib.ExitStack() as stack:
        if not _acquire(stack, say):
            return EXIT_BUSY
        now = clock()
        run_id = trace.start_run()
        report = RunReport()
        trace.log_event(run_id, "harness", "decision", "run_outer",
                        f"start: dry_run={opts.dry_run} approval={opts.approve} measure_only={opts.measure_only} "
                        f"min_score={opts.min_score}", ok=True)
        say(f"run {run_id}  (dry_run={opts.dry_run}, approval={opts.approve})")
        cap, used, unreadable = quota.run_cap(now)
        note = f" ({unreadable} unreadable trace files, so this may be low)" if unreadable else ""
        trace.log_event(run_id, "harness", "decision", "daily guard",
                        f"{used} model requests in the last 24 hours{note}; this run may make {cap}", ok=cap > 0)
        if unreadable:
            report.warnings.append(f"{unreadable} unreadable trace files: the daily request count may be low")
        say(f"model requests: {used} in the last 24 hours, {cap} allowed this run")
        with run_budget(cap) as budget:
            code = _run(llm, brief, opts, run_id, now, budget, report, input_fn, clock, say)
        _log_summary(run_id, code, opts, budget, used, report)
        say(f"trace: {trace.run_path(run_id)}")
        return code


def _log_summary(run_id: str, code: int, opts: OuterOptions, budget: Budget, used_24h: int, report: RunReport) -> None:
    """The run's last event, for the dashboard: complete JSON (never truncated) and its hash, so a reader can
    check the summary is the one the run wrote. Redacted before hashing, because the trace redacts what it stores."""
    body = trace.redact(json.dumps({
        "schema_version": SUMMARY_SCHEMA_VERSION, "run_id": run_id, "exit_code": code, "dry_run": opts.dry_run,
        "requests": {"used": budget.used, "limit": budget.limit}, "requests_last_24h_before_run": used_24h,
        "plan": report.plan, "outcomes": report.outcomes, "learnings": report.learnings, "warnings": report.warnings,
    }, ensure_ascii=False))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    trace.log_event(run_id, "harness", "decision", f"run_summary sha256={digest}", body,
                    ok=code in (EXIT_OK, EXIT_ESCALATED), truncate=False)


def _run(llm: LLM, brief: BrandBrief, opts: OuterOptions, run_id: str, now: datetime, budget: Budget,
         report: RunReport, input_fn: Callable[[str], str], clock: Clock, say: Callable[[str], None]) -> int:
    def log(summary_in: str, summary_out: str, ok: bool = True) -> None:
        trace.log_event(run_id, "harness", "decision", summary_in, summary_out, ok=ok)

    # 1. Learn from posts that have had time to collect engagement.
    measure_budget = Budget(quota.MEASURE_REQUEST_CAP, parent=budget)
    try:
        measured = measure_posts(llm, run_id, now, dry_run=opts.dry_run, budget=measure_budget)
    except ApprovedLogError as e:
        log("approved log pre-check", str(e), ok=False)
        say(f"blocked before writing: {e}")
        report.outcome(None, "blocked", f"approved log unreadable: {e}")
        return EXIT_BLOCKED
    report.learnings = {"saved": measured.learned, "skipped": measured.skipped}
    if measured.stopped:
        report.warnings.append(f"measure: {measured.stopped}")
    for line in [*measured.skipped, *([measured.stopped] if measured.stopped else [])]:
        say(f"measure: {line}")
    if measured.learned:
        say(f"measure: saved learnings for {', '.join(measured.learned)}")
    if opts.measure_only:
        report.outcome(None, "skipped", "measure only")
        return EXIT_OK

    # 2. Only a post that can publish today is worth writing (decision 4.3): check headroom before any model call.
    try:
        published = live_records()
    except ApprovedLogError as e:
        log("approved log pre-check", str(e), ok=False)
        say(f"blocked before writing: {e}")
        report.outcome(None, "blocked", f"approved log unreadable: {e}")
        return EXIT_BLOCKED
    rate = guardrails.check_rate_cap(now, published)
    if not rate["ok"]:
        reason = "; ".join(rate["reasons"])
        log("rate cap pre-check", reason, ok=False)
        report.outcome(None, "skipped", f"no headroom: {reason}")
        say(f"no headroom to post: {reason}")
        return EXIT_OK  # a schedule should not read "nothing to do yet" as an error

    # 3. Pick the next due post, planning a new week only when nothing is waiting.
    try:
        state = plan_state.load_state()
    except PlanStateError as e:
        log("plan state", f"refused: {e}", ok=False)
        say(f"refused: {e}")
        report.outcome(None, "skipped", f"refused: {e}")
        return EXIT_REFUSED
    today = now.astimezone(timezone.utc).date()

    def save() -> bool:
        if opts.dry_run:
            return True  # a dry run reads the real state but never writes it
        try:
            plan_state.save_state(state)
        except (OSError, LockTimeout) as e:
            log("plan state", f"write failed: {type(e).__name__}", ok=False)
            say(f"warning: plan state could not be saved ({type(e).__name__})")
            report.warnings.append(f"plan state could not be saved ({type(e).__name__})")
            return False
        return True

    # A post can be live while its plan state still says "planned" (a crash or failed save after publishing):
    # approved.jsonl is the record of what went out, so it wins before anything is selected and written again.
    settled = plan_state.reconcile(state, published, run_id, now)
    if settled:
        reason = "settled from approved.jsonl: " + ", ".join(f"{p.id} {p.status}" for p in settled)
        log("plan state", reason, ok=False)
        say(f"warning: {reason}")
        report.warnings.append(reason)
        save()

    post = plan_state.select_due(state, today, run_id, now)
    if post is None and not state.has_active():
        try:
            learnings = fetch_learnings(run_id)
            week = plan_week(llm, run_id, brief, learnings, today)
        except (LLMError, ToolRefused, OSError) as e:
            log("plan", f"failed: {type(e).__name__}: {e}", ok=False)
            say(f"failed to plan: {e}")
            report.outcome(None, "failed", f"planning failed: {type(e).__name__}: {e}")
            return EXIT_FAILED
        added = plan_state.add_plan(state, week, run_id, now, {r.get("post_id") for r in published})
        log("plan", f"planned {len(added)} posts: " + ", ".join(f"{p.id} {p.day}" for p in added))
        report.plan = {"plan_id": added[0].plan_id, "rationale": week.rationale,
                       "posts": [{"id": p.id, "day": p.day.isoformat(), "topic": p.topic, "angle": p.angle,
                                  "goal": p.goal} for p in added]}
        say(f"planned {len(added)} posts for the week")
        if not save():
            report.outcome(None, "failed", "the new plan could not be saved")
            return EXIT_FAILED  # unsaved ids would be lost, and the next run would plan (and spend) again
        post = plan_state.select_due(state, today, run_id, now)
    if post is None:
        waiting = [p for p in state.posts if p.status in plan_state.ACTIVE]
        reason = f"no post due today; {len(waiting)} waiting"
        if waiting:
            reason += f", next on {min(p.day for p in waiting)}"
        log("select post", reason)
        report.outcome(None, "skipped", reason)
        say(reason)
        save()  # select_due may have carried posts forward
        return EXIT_OK
    log("select post", f"{post.id} topic={post.topic!r} day={post.day} status={post.status}")
    say(f"post {post.id}: {post.topic} ({post.goal})")

    # 4. Write and critique.
    result = run_inner(llm, run_id, post.planned_post(), brief, min_score=opts.min_score)
    _show_attempts(result, say)
    if result.status != "passed":
        # Only a loop cut short by an error can be the cap's doing: three weak drafts that happen to use the
        # last request are a real escalation, and must not come back next run without a strike.
        capped = result.error is not None and budget.used >= budget.limit
        return _end_unpassed(result, capped, state, post, run_id, now, save, say, report)

    # 5. Guardrails (human approval last), then publish.
    final = result.final
    assert final is not None  # "passed" always has an attempt
    gate = guardrails.run_all(final.draft.text, brief.model_dump(), run_id=run_id, now=now, published_log=published,
                              recent_texts=[r["text"] for r in published], approval_enabled=opts.approve,
                              input_fn=input_fn)
    if not gate["ok"]:
        soft = all(r.startswith(("check_rate_cap", "require_approval: skipped")) or _NO_ONE_THERE in r
                   for r in gate["reasons"])
        return _end_gate(state, post, run_id, now, save, say, report, "carried_forward" if soft else "blocked",
                         "blocked: " + "; ".join(gate["reasons"]))
    try:
        record = publish(run_id, final.draft, final.critique, brief, approved=True, dry_run=opts.dry_run,
                         min_score=opts.min_score, clock=clock)
    except PublishBlocked as e:
        only_rate = all(r.startswith("check_rate_cap") for r in e.reasons)
        return _end_gate(state, post, run_id, now, save, say, report, "carried_forward" if only_rate else "blocked",
                         f"blocked at publish: {e}")
    except PublishRefused as e:
        waits = "publish lock" in str(e)
        return _end_gate(state, post, run_id, now, save, say, report, "carried_forward" if waits else "failed",
                         f"refused: {e}")
    except Exception as e:  # noqa: BLE001 - a client error here may mean the post is live; never retry it
        reason = f"publish failed, outcome unknown ({type(e).__name__}): check the account"
        plan_state.mark(state, post.id, "failed", run_id, now, reason)
        save()
        with contextlib.suppress(trace.TraceWriteError):
            log(f"publish {post.id}", reason, ok=False)
        say(f"{reason}. The pending row keeps counting toward the rate cap.")
        report.outcome(post.id, "failed", reason)
        return EXIT_FAILED
    plan_state.mark(state, post.id, "published", run_id, now, "published", uri=record["uri"])
    with contextlib.suppress(trace.TraceWriteError):
        log(f"publish {post.id}", f"published: {record['uri']}")
    for warning in record["warnings"]:
        say(f"warning: {warning}")
        report.warnings.append(warning)
    if not save():
        say(f"warning: {post.id} is live but its plan state was not saved; the next run settles it from approved.jsonl")
    report.outcome(post.id, "published", "published", uri=record["uri"])
    say(f"published: {record['uri']}")
    return EXIT_OK


def _show_attempts(result: InnerResult, say: Callable[[str], None]) -> None:
    for i, a in enumerate(result.attempts, 1):
        c = a.critique
        say(f"\nattempt {i}: {a.draft.text}\n  scores voice={c.voice} clarity={c.clarity} cta={c.cta} "
            f"policy_risk={c.policy_risk}\n" + "\n".join(f"  {k}: {v}" for k, v in c.reasons.items()))


def _end_unpassed(result: InnerResult, capped: bool, state: PlanState, post: PostRecord, run_id: str,
                  now: datetime, save: Callable[[], bool], say: Callable[[str], None], report: RunReport) -> int:
    if capped:
        # The run ran out of requests, not the post out of chances: it goes back in the queue, no strike against it.
        plan_state.mark(state, post.id, "carried_forward", run_id, now, "run request cap reached")
        save()
        say("stopped: the run's request cap was reached; the post is carried forward")
        report.outcome(post.id, "carried_forward", "run request cap reached")
        return EXIT_OK
    if result.status == "failed":
        updated = plan_state.record_failed_run(state, post.id, run_id, now, f"no draft: {result.error}")
        save()
        say(f"failed: {result.error} (post is now {updated.status})")
        report.outcome(post.id, updated.status, f"no draft: {result.error}")
        return EXIT_FAILED
    reason = f"escalated after {len(result.attempts)} attempts"
    plan_state.mark(state, post.id, "escalated", run_id, now, reason)
    save()
    say(f"{reason}: needs human review; nothing published (re-queue with --requeue {post.id})")
    report.outcome(post.id, "escalated", reason + (f" ({result.error})" if result.error else ""))
    return EXIT_ESCALATED


def _end_gate(state: PlanState, post: PostRecord, run_id: str, now: datetime, save: Callable[[], bool],
              say: Callable[[str], None], report: RunReport, status: plan_state.Status, reason: str) -> int:
    plan_state.mark(state, post.id, status, run_id, now, reason)
    save()
    with contextlib.suppress(trace.TraceWriteError):
        trace.log_event(run_id, "harness", "decision", f"publish {post.id}", f"{status}: {reason}", ok=False)
    say(f"{reason} (post is now {status})")
    report.outcome(post.id, status, reason)
    return EXIT_FAILED if status == "failed" else EXIT_BLOCKED
