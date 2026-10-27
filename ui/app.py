"""The local Autopilot app: the terminal's run, approval and requeue, plus quota and GitHub status, on one page.

    python -m ui.app           # serve on http://127.0.0.1:7860
    python -m ui.app --open    # and open it in its own Edge window (what Autopilot.bat does)

Bound to 127.0.0.1 with no share link and analytics off: the page can publish, so nothing off this machine may
reach it. Requires requirements-ui.txt.
"""

from __future__ import annotations

import os

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"  # read when gradio is imported, so it is set first

import argparse  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import webbrowser  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from typing import Any  # noqa: E402

import gradio as gr  # noqa: E402

from harness.env import load_dotenv  # noqa: E402
from harness.publish import utc_now  # noqa: E402
from scripts.run_outer import DEFAULT_ENV_FILE  # noqa: E402
from ui import repo  # noqa: E402
from ui.controller import (  # noqa: E402
    PLAN_HEADERS,
    Controller,
    Snapshot,
    budget_line,
    plan_rows,
    quota_text,
    rate_text,
)

HOST, PORT = "127.0.0.1", 7860
URL = f"http://{HOST}:{PORT}"
_QUESTION = "Publish this post? [y/N]"


def _run_note(s: Snapshot) -> str:
    if s.running:
        mode = "Dry run" if s.dry_run else "Live run"
        return f"**{mode} in progress.**" + (" Waiting for your answer below." if s.approval else "")
    if s.exit_code is not None:
        return f"Last run finished with exit code {s.exit_code}. See the log."
    return "Idle. A run measures old posts, then writes, checks and (with your approval) publishes the next due post."


def _card_title(s: Snapshot) -> str:
    if s.approval is None:
        return ""
    if s.approval.dry_run:
        return "**Dry run.** Approving publishes to a `dryrun://` address only. Nothing goes to Bluesky."
    return "**Live run. Approving publishes this post to Bluesky now.**"


def build(ctl: Controller) -> gr.Blocks:
    with gr.Blocks(title="Autopilot", analytics_enabled=False) as demo:
        gr.Markdown("# Autopilot")
        with gr.Tab("Run"):
            budget = gr.Markdown()
            with gr.Row():
                live_btn = gr.Button("Run next post", variant="primary")
                dry_btn = gr.Button("Dry run")
            # A live run is one click from a real post (after approval), so it takes a second, deliberate click.
            with gr.Group(visible=False) as confirm:
                gr.Markdown("**Start a live run?** If the draft passes, you will be asked to approve it, and "
                            "approving publishes it to Bluesky.")
                with gr.Row():
                    confirm_btn = gr.Button("Yes, start the live run", variant="primary")
                    cancel_btn = gr.Button("Cancel")
            run_note = gr.Markdown()
            with gr.Group(visible=False) as card:
                card_title = gr.Markdown()
                draft = gr.Textbox(label="Draft", lines=6, interactive=False)
                with gr.Row():
                    approve_btn = gr.Button("Approve", variant="primary")
                    later_btn = gr.Button("Not now (try again next run)")
                    reject_btn = gr.Button("Reject (block this post)", variant="stop")
            answer_note = gr.Markdown()
            log = gr.Textbox(label="Log", lines=18, max_lines=18, autoscroll=True, interactive=False)
        with gr.Tab("Plan") as plan_tab:
            rationale = gr.Markdown()
            table = gr.Dataframe(headers=PLAN_HEADERS, interactive=False, wrap=True)
            with gr.Row():
                escalated = gr.Dropdown(label="Escalated posts", choices=[], scale=3)
                requeue_btn = gr.Button("Requeue", scale=1)
            plan_note = gr.Markdown()
        with gr.Tab("Status") as status_tab:
            quota_md = gr.Markdown()
            rate_md = gr.Markdown()
            github_md = gr.Markdown()
            with gr.Row():
                refresh_btn = gr.Button("Refresh")
                pull_btn = gr.Button("Pull from GitHub")
                save_btn = gr.Button("Save to GitHub")
            status_note = gr.Markdown()

        approval_id = gr.State(0)
        seen = gr.State(None)  # what this page last drew, so an unchanged tick sends nothing

        def tick(last: Any) -> Any:
            s = ctl.snapshot()
            key = (s.running, s.dry_run, s.log, s.approval, s.exit_code)
            if key == last:
                return (gr.skip(),) * 10
            just_finished = last is not None and last[0] and not s.running
            prompt = s.approval.prompt.strip().removesuffix(_QUESTION).strip() if s.approval else ""
            return (_run_note(s), gr.update(visible=s.approval is not None), _card_title(s), prompt,
                    s.approval.id if s.approval else 0, s.log, gr.update(interactive=not s.running),
                    gr.update(interactive=not s.running), key, budget_line() if just_finished else gr.skip())

        gr.Timer(1.0).tick(tick, inputs=seen, outputs=[run_note, card, card_title, draft, approval_id, log,
                                                       live_btn, dry_btn, seen, budget])
        # Counting reads every trace file, so the line refreshes on load, when a run ends and every 30 s, not every tick.
        demo.load(budget_line, outputs=budget)
        gr.Timer(30.0).tick(budget_line, outputs=budget)
        live_btn.click(lambda: (gr.update(visible=True), ""), outputs=[confirm, answer_note])
        cancel_btn.click(lambda: (gr.update(visible=False), "Live run cancelled."), outputs=[confirm, answer_note])
        confirm_btn.click(lambda: (gr.update(visible=False), ctl.start(dry_run=False)), outputs=[confirm, answer_note])
        dry_btn.click(lambda: (gr.update(visible=False), ctl.start(dry_run=True)), outputs=[confirm, answer_note])
        approve_btn.click(lambda i: ctl.answer(i, "approve"), inputs=approval_id, outputs=answer_note)
        later_btn.click(lambda i: ctl.answer(i, "not_now"), inputs=approval_id, outputs=answer_note)
        reject_btn.click(lambda i: ctl.answer(i, "reject"), inputs=approval_id, outputs=answer_note)

        def load_plan() -> tuple[str, list[list[str]], Any]:
            text, rows, ids = plan_rows()
            return text, rows, gr.update(choices=ids, value=ids[0] if ids else None)

        def requeue(post_id: str | None) -> tuple[str, str, list[list[str]], Any]:
            note = ctl.requeue(post_id) if post_id else "Pick an escalated post first."
            return (note, *load_plan())

        plan_tab.select(load_plan, outputs=[rationale, table, escalated])
        requeue_btn.click(requeue, inputs=escalated, outputs=[plan_note, rationale, table, escalated])

        def load_status() -> tuple[str, str, str]:
            now = utc_now()
            try:
                github = repo.status()
            except repo.RepoError as e:
                github = f"Could not check GitHub: {e}"
            return quota_text(now), rate_text(now), github

        def git_action(action: str) -> str:
            if ctl.busy():
                return "A run is going. Try again after it finishes."
            try:
                if action == "pull":
                    return repo.pull()
                url = repo.save_data_pr(utc_now())
                return f"Opened a PR for you to review and merge: {url}" if url.startswith("http") else url
            except repo.RepoError as e:
                return str(e)

        status_tab.select(load_status, outputs=[quota_md, rate_md, github_md])
        refresh_btn.click(load_status, outputs=[quota_md, rate_md, github_md])
        pull_btn.click(lambda: git_action("pull"), outputs=status_note).then(
            load_status, outputs=[quota_md, rate_md, github_md])
        save_btn.click(lambda: git_action("save"), outputs=status_note).then(
            load_status, outputs=[quota_md, rate_md, github_md])
    return demo


def _already_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _open_window() -> None:
    """Edge's --app mode gives the page its own window with no tabs or address bar; any browser will do otherwise."""
    if sys.platform == "win32":
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "msedge", f"--app={URL}"])  # noqa: S603, S607
            return
        except OSError:
            pass
    webbrowser.open(URL)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ui.app", description="The local Autopilot app.")
    p.add_argument("--open", action="store_true", help="open the app in its own window once it is up")
    args = p.parse_args(argv)
    if _already_running():
        print(f"Autopilot is already running at {URL}", flush=True)
        if args.open:
            _open_window()
        return 0
    load_dotenv(DEFAULT_ENV_FILE)  # so the log can redact the real secret values from the first message
    ctl = Controller()
    demo = build(ctl)
    demo.launch(server_name=HOST, server_port=PORT, share=False, inbrowser=False, prevent_thread_lock=True,
                ssr_mode=False, mcp_server=False, quiet=True)
    print(f"Autopilot is running at {URL}. Close this window to stop it.", flush=True)
    if args.open:
        _open_window()
    try:
        demo.block_thread()
    finally:
        ctl.shutdown()
        demo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
