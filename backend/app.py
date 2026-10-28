"""The hosted backend: the web app's only way to start a run or answer an approval.

It is the local app's Controller behind HTTP, with every run wrapped in db_sync.hosted_data_dir, so a hosted run
is the terminal's run_outer on a working folder pulled from Postgres. The web app reads plans, posts and traces
from Postgres directly; this server only does what needs the secrets (model calls and Bluesky).

Auth is a shared secret in X-Autopilot-Secret, compared in constant time; only /health is open, so the free
host's public URL can be woken without the secret. Run with one worker (`--workers 1`): the run and its pending
approval live in this process. Deployed to Render from render.yaml and backend/Dockerfile.

    uvicorn --factory backend.app:create_app --port 10000 --workers 1
"""

from __future__ import annotations

import contextlib
import hmac
import os
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from harness.db_store import PostgresStore
from harness.db_sync import Store, StoreBusy, SyncError, hosted_data_dir
from ui.controller import Choice, Controller, Requeuer, Runner, _requeue, _run_outer, _run_post

SECRET_ENV = "AUTOPILOT_BACKEND_SECRET"
SECRET_HEADER = "X-Autopilot-Secret"
MIN_SECRET_LEN = 32
EXIT_BUSY = 6
EXIT_NOT_SAVED = 7

StoreFactory = Callable[[], Store]


def _close(store: Store) -> None:
    close = getattr(store, "close", None)
    if close is not None:
        close()


def _in_hosted_dir(store_factory: StoreFactory, work: Callable[[], int], say: Callable[[str], None]) -> int:
    """A fresh connection per run: Neon drops idle ones, and a run may start hours after the last."""
    store = store_factory()
    try:
        with tempfile.TemporaryDirectory(prefix="autopilot-", ignore_cleanup_errors=True) as tmp:
            try:
                with hosted_data_dir(store, Path(tmp)):
                    return work()
            except StoreBusy as e:
                say(f"refused: {e} (the daily cron or another run); try again in a few minutes")
                return EXIT_BUSY
            except SyncError as e:
                say(f"error: the run finished but its state was not fully saved: {e}")
                return EXIT_NOT_SAVED
    finally:
        _close(store)


def hosted_runner(runner: Runner, store_factory: StoreFactory) -> Runner:
    def run(argv: list[str], input_fn: Callable[[str], str], say: Callable[[str], None]) -> int:
        return _in_hosted_dir(store_factory, lambda: runner(argv, input_fn, say), say)
    return run


def hosted_requeuer(requeuer: Requeuer, store_factory: StoreFactory) -> Requeuer:
    def requeue(post_id: str, say: Callable[[str], None]) -> int:
        return _in_hosted_dir(store_factory, lambda: requeuer(post_id, say), say)
    return requeue


def hosted_controller(store_factory: StoreFactory = PostgresStore.from_env) -> Controller:
    return Controller(runner=hosted_runner(_run_outer, store_factory),
                      post_runner=hosted_runner(_run_post, store_factory),
                      requeuer=hosted_requeuer(_requeue, store_factory))


class RunRequest(BaseModel):
    """Only these kinds exist, and approval cannot be switched off from here: the argv is built by the controller."""

    kind: Literal["next", "topic", "plan"]
    dry_run: bool = False
    topic: str | None = Field(default=None, max_length=200)
    angle: str | None = Field(default=None, max_length=300)
    goal: Literal["awareness", "engagement", "click"] = "engagement"


class AnswerRequest(BaseModel):
    choice: Choice


class Message(BaseModel):
    message: str


class ApprovalOut(BaseModel):
    id: int
    prompt: str
    dry_run: bool


class StatusOut(BaseModel):
    running: bool
    what: str
    dry_run: bool
    log: str
    approval: ApprovalOut | None
    exit_code: int | None


def create_app(controller: Controller | None = None, secret: str | None = None) -> FastAPI:
    """Refuses to start without a long secret: an open endpoint here could post to the account."""
    secret = secret if secret is not None else os.environ.get(SECRET_ENV, "")
    if len(secret) < MIN_SECRET_LEN:
        raise RuntimeError(f"{SECRET_ENV} must be set to at least {MIN_SECRET_LEN} characters")
    ctl = controller or hosted_controller()
    expected = secret.encode()

    def require_secret(x_autopilot_secret: str = Header(default="")) -> None:
        if not hmac.compare_digest(x_autopilot_secret.encode(), expected):
            raise HTTPException(status_code=401, detail="unauthorized")

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        ctl.shutdown()  # a pending approval reads as "no answer", so the post is carried forward and the lock freed

    app = FastAPI(title="autopilot", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    auth = [Depends(require_secret)]

    @app.get("/health")
    def health() -> dict[str, bool]:
        """Open and empty, so the web app can wake a sleeping service without sending the secret."""
        return {"ok": True}

    @app.get("/status", dependencies=auth)
    def status() -> StatusOut:
        s = ctl.snapshot()
        approval = ApprovalOut(id=s.approval.id, prompt=s.approval.prompt, dry_run=s.approval.dry_run) \
            if s.approval else None
        return StatusOut(running=s.running, what=s.what, dry_run=s.dry_run, log=s.log, approval=approval,
                         exit_code=s.exit_code)

    @app.post("/runs", dependencies=auth, status_code=202)
    def start_run(req: RunRequest) -> Message:
        if ctl.busy():
            raise HTTPException(status_code=409, detail="A run is already going. Wait for it to finish.")
        if req.kind == "topic":
            if not (req.topic or "").strip():
                raise HTTPException(status_code=422, detail="Write a topic first.")
            return Message(message=ctl.start_topic(req.topic, req.angle, req.goal, dry_run=req.dry_run))
        if req.kind == "plan":
            return Message(message=ctl.plan_now())
        return Message(message=ctl.start(dry_run=req.dry_run))

    @app.post("/approvals/{approval_id}", dependencies=auth)
    def answer(approval_id: int, req: AnswerRequest) -> Message:
        snapshot = ctl.snapshot()
        if snapshot.approval is None or snapshot.approval.id != approval_id:
            raise HTTPException(status_code=409, detail="That draft is no longer waiting for an answer.")
        return Message(message=ctl.answer(approval_id, req.choice))

    @app.post("/posts/{post_id}/requeue", dependencies=auth)
    def requeue(post_id: str) -> Message:
        if ctl.busy():
            raise HTTPException(status_code=409, detail="A run is going. Requeue after it finishes.")
        return Message(message=ctl.requeue(post_id))

    return app
