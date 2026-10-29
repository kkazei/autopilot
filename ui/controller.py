"""Runs the outer loop for the hosted backend (backend/app.py), one run at a time, and turns its approval prompt into
an answer the web app can give.

It started as the local Gradio app's runner (archived in the local-app-final release). A run goes through
scripts.run_outer.main, the same entry point as the terminal, so every harness check and the outer lock still apply:
the controller only changes where messages go and where the approval answer comes from.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from harness import trace

# Long enough to read a draft and check a fact; short enough that a forgotten window doesn't hold the outer lock
# for hours. Timing out reads as "nobody was there", so the post is carried forward rather than blocked.
APPROVAL_TIMEOUT_S = 15 * 60
LOG_LIMIT = 400  # messages; a run says a few dozen, so this only bites on a runaway
EXIT_MEANINGS = {0: "done", 2: "refused", 3: "escalated: needs human review", 4: "failed", 5: "blocked",
                 6: "another run is active", 7: "not saved to the database"}

Choice = Literal["approve", "not_now", "reject"]
# What each button feeds the harness's approval prompt. "Not now" is None: it ends the wait the way the timeout does.
_ANSWERS: dict[str, str | None] = {"approve": "y", "reject": "n", "not_now": None}
_REPLIES = {"approve": "Approved.", "reject": "Rejected: this post is blocked for good.",
            "not_now": "Not now: the post is carried forward to the next run."}

Runner = Callable[[list[str], Callable[[str], str], Callable[[str], None]], int]
Requeuer = Callable[[str, Callable[[str], None]], int]


def _run_outer(argv: list[str], input_fn: Callable[[str], str], say: Callable[[str], None]) -> int:
    from scripts import run_outer  # imported late so tests can build a Controller without the model client

    return run_outer.main(argv, input_fn=input_fn, say=say)


def _run_post(argv: list[str], input_fn: Callable[[str], str], say: Callable[[str], None]) -> int:
    from scripts import run_post

    return run_post.main(argv, input_fn=input_fn, say=say)


def _requeue(post_id: str, say: Callable[[str], None]) -> int:
    from scripts import run_outer

    return run_outer.main(["--requeue", post_id], say=say)


@dataclass(frozen=True)
class Approval:
    id: int
    prompt: str
    dry_run: bool


@dataclass(frozen=True)
class Snapshot:
    running: bool
    what: str  # "next post", "topic post" or "plan now": the page says which kind of run is going
    dry_run: bool
    log: str
    approval: Approval | None
    exit_code: int | None


class Controller:
    def __init__(self, runner: Runner = _run_outer, requeuer: Requeuer = _requeue, post_runner: Runner = _run_post,
                 approval_timeout_s: float = APPROVAL_TIMEOUT_S, log_limit: int = LOG_LIMIT) -> None:
        self._runner = runner
        self._post_runner = post_runner
        self._requeuer = requeuer
        self._timeout_s = approval_timeout_s
        self._mutex = threading.Lock()
        self._log: deque[str] = deque(maxlen=log_limit)
        self._thread: threading.Thread | None = None
        self._dry_run = False
        self._what = "next post"
        self._exit_code: int | None = None
        self._approval: Approval | None = None
        self._answer: str | None = None
        self._answered = threading.Event()
        self._approval_ids = 0

    def say(self, message: str) -> None:
        """Redacted on the way in, so nothing unredacted is ever held in memory for the page to show."""
        with self._mutex:
            self._log.append(trace.redact(message))

    def busy(self) -> bool:
        with self._mutex:
            return self._busy()

    def _busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, *, dry_run: bool) -> str:
        """The next due post, exactly as the terminal's run_outer does it."""
        started = self._launch(self._runner, ["--dry-run"] if dry_run else [], dry_run, "next post")
        return started or ("Dry run started." if dry_run else "Live run started.")

    def start_topic(self, topic: str | None, angle: str | None, goal: str, *, dry_run: bool) -> str:
        """One post on a person's topic, through run_post: the same checks, rate cap and approval as any post."""
        topic, angle = (topic or "").strip(), (angle or "").strip()
        if not topic:
            return "Write a topic first."
        argv = ["--topic", topic, "--goal", goal, *(["--angle", angle] if angle else []),
                *(["--dry-run"] if dry_run else [])]
        started = self._launch(self._post_runner, argv, dry_run, "topic post")
        return started or ("Dry run of the topic post started." if dry_run else "Live topic post started.")

    def plan_now(self) -> str:
        """Next week's plan, ahead of time. The harness refuses while any post is waiting, at no model cost."""
        return self._launch(self._runner, ["--plan-only"], False, "plan now") or "Planning started."

    def measure_now(self) -> str:
        """Reads engagement now instead of waiting for the daily schedule: the same --measure-only run, no drafts."""
        return self._launch(self._runner, ["--measure-only"], False, "measure") or "Measuring started."

    def _launch(self, runner: Runner, argv: list[str], dry_run: bool, what: str) -> str | None:
        """Starts the run, or says why not. One run at a time, whatever kind."""
        with self._mutex:
            if self._busy():
                return "A run is already going. Wait for it to finish."
            self._log.clear()
            self._dry_run, self._what = dry_run, what
            self._exit_code = None
            # Not a daemon: closing the app waits for the run to unwind, so the outer lock is released.
            self._thread = threading.Thread(target=self._work, args=(runner, argv), name="autopilot-run")
            self._thread.start()
        return None

    def _work(self, runner: Runner, argv: list[str]) -> None:
        try:
            code: int | None = runner(argv, self._ask, self.say)
        except Exception as e:  # noqa: BLE001 - the app must outlive a crashed run and say what happened
            code = None
            self.say(f"the run crashed ({type(e).__name__}: {e}); check the trace and the terminal output")
        with self._mutex:
            self._exit_code = code
            self._approval = None
        if code is not None:
            self.say(f"finished: exit code {code} ({EXIT_MEANINGS.get(code, 'unknown')})")

    def _ask(self, prompt: str) -> str:
        """The run's input_fn: show the draft, then wait for a button. "Not now", silence and closing the app all
        raise EOFError, which the harness already reads as "no approval input" and carries the post forward."""
        with self._mutex:
            self._approval_ids += 1
            self._approval = Approval(self._approval_ids, prompt, self._dry_run)
            self._answer = None
            self._answered.clear()
        answered = self._answered.wait(self._timeout_s)
        with self._mutex:
            self._approval = None
            answer = self._answer
        if not answered:
            self.say(f"no answer within {self._timeout_s / 60:g} minutes; the post is carried forward")
        if answer is None:
            raise EOFError("no approval input")
        return answer

    def answer(self, approval_id: int, choice: Choice) -> str:
        """Only the card on screen can be answered, once: a double tap or a stale page does nothing."""
        with self._mutex:
            if self._approval is None or self._approval.id != approval_id or self._answered.is_set():
                return "That draft is no longer waiting for an answer."
            self._answer = _ANSWERS[choice]
            self._answered.set()
        return _REPLIES[choice]

    def snapshot(self) -> Snapshot:
        with self._mutex:
            return Snapshot(running=self._busy(), what=self._what, dry_run=self._dry_run, log="\n".join(self._log),
                            approval=self._approval, exit_code=self._exit_code)

    def requeue(self, post_id: str) -> str:
        if self.busy():
            return "A run is going. Requeue after it finishes."
        lines: list[str] = []
        self._requeuer(post_id, lambda m: lines.append(trace.redact(m)))
        return "\n".join(lines)

    def shutdown(self, wait_s: float = 120.0) -> None:
        """A pending approval is answered with silence, so the run carries its post forward and lets go of the lock."""
        with self._mutex:
            thread = self._thread
            if self._approval is not None and not self._answered.is_set():
                self._answer = None
                self._answered.set()
        if thread is not None:
            thread.join(wait_s)
