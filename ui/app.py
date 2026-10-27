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
import html  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import webbrowser  # noqa: E402
from collections.abc import Sequence  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import gradio as gr  # noqa: E402

from harness import trace  # noqa: E402
from harness.env import load_dotenv  # noqa: E402
from harness.guardrails import MAX_POST_CHARS  # noqa: E402
from harness.publish import utc_now  # noqa: E402
from harness.schemas import BrandBrief  # noqa: E402
from scripts.run_outer import DEFAULT_ENV_FILE  # noqa: E402
from ui import repo  # noqa: E402
from ui.controller import (  # noqa: E402
    Budget,
    Controller,
    Snapshot,
    budget,
    plan_rows,
    quota_text,
    rate_text,
    topic_choices,
)

HOST, PORT = "127.0.0.1", 7860
URL = f"http://{HOST}:{PORT}"
_DRAFT_RE = re.compile(r"--- draft \(\d+ chars\) ---\n(.*)\n--- end ---", re.DOTALL)
_SCORES_RE = re.compile(r"scores voice=(\d) clarity=(\d) cta=(\d) policy_risk=(\d)")
_CONFIRM = {
    "next": "Autopilot will write the next due post and check it. If the draft passes, you decide whether it "
            "goes out; approving publishes it to Bluesky.",
    "topic": "Autopilot will write a post on this topic and check it. If the draft passes, you decide whether it "
             "goes out; approving publishes it to Bluesky.",
}
# Every event is private: Gradio's client libraries cannot call it, so Start and Approve come from this page.
# A hand-built HTTP request from this machine still could, as could the CLI; nothing off this machine can.
_PRIVATE: dict[str, Any] = {"api_visibility": "private"}
_QUIET: dict[str, Any] = {**_PRIVATE, "show_progress": "hidden"}  # background refreshes: no "processing" flicker
_EXIT_WORDS = {0: "done", 2: "refused", 3: "escalated", 4: "failed", 5: "blocked", 6: "busy"}
_STATUS_TONE = {"published": "ok", "planned": "info", "carried_forward": "warn", "escalated": "warn",
                "blocked": "bad", "failed": "bad"}

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.indigo,
    neutral_hue=gr.themes.colors.zinc,
    radius_size=gr.themes.sizes.radius_md,
    font=["Segoe UI Variable Text", "Segoe UI", "system-ui", "sans-serif"],
    font_mono=["Cascadia Mono", "Consolas", "ui-monospace", "monospace"],
).set(body_background_fill="#f5f6f8", body_background_fill_dark="#101217")
CSS = (Path(__file__).with_name("app.css")).read_text(encoding="utf-8")
HEAD = "<script>\n" + (Path(__file__).with_name("app.js")).read_text(encoding="utf-8") + "\n</script>"


def _brand_name() -> str:
    try:
        return BrandBrief.model_validate_json((trace.data_dir() / "brand_brief.json").read_text(encoding="utf-8")).name
    except (OSError, ValueError):
        return "Your post"


def _state_html(s: Snapshot) -> str:
    """The pill in the top bar: what the app is doing right now, readable from across the room."""
    if s.running and s.approval:
        tone, text = "warn", "Waiting for you"
    elif s.running:
        what = "Planning" if s.what == "plan now" else f"{'Dry run' if s.dry_run else 'Live run'}: {s.what}"
        tone, text = "info running", f"{what}"
    elif s.exit_code is None:
        tone, text = "neutral", "Idle"
    else:
        tone = {0: "ok", 3: "warn", 6: "warn"}.get(s.exit_code, "bad")
        text = f"Last run: {_EXIT_WORDS.get(s.exit_code, f'exit {s.exit_code}')}"
    return f'<span class="ap-pill {tone}" role="status">{html.escape(text)}</span>'



def _budget_html(b: Budget) -> tuple[str, str]:
    """(the meter for the top bar, the low-quota warning under it)."""
    left = max(0, b.limit - b.used)
    pct = min(100, round(100 * b.used / b.limit)) if b.limit else 100
    tone = "bad" if left == 0 else "warn" if b.low else "ok"
    note = f" ({b.unreadable} traces unreadable)" if b.unreadable else ""
    posting_tone = "ok" if b.posting_ok else "warn"
    return (
        f'<div class="ap-budget">'
        f'<div class="ap-meter-group" title="Model requests in the last 24 hours, counted from the traces">'
        f'<span class="ap-label">Requests</span>'
        f'<span class="ap-meter {tone}" role="meter" aria-valuemin="0" aria-valuemax="{b.limit}" '
        f'aria-valuenow="{b.used}" aria-label="Model requests used"><span style="width:{pct}%"></span></span>'
        f'<span class="ap-num">{b.used}/{b.limit}</span>'
        f'<span class="ap-sub">next run ≤ {b.next_cap}{html.escape(note)}</span></div>'
        f'<span class="ap-pill {posting_tone}" title="{html.escape(b.posting)}">Posting: '
        f'{"OK" if b.posting_ok else "waiting"}</span></div>',
        '<p class="ap-warning">Few requests left: a run may stop part-way. Waiting until the count drops is '
        'safer.</p>' if b.low else "",
    )


def _draft_text(prompt: str) -> str:
    m = _DRAFT_RE.search(prompt)
    return m.group(1) if m else prompt.strip().removesuffix("Publish this post? [y/N]").strip()


def _approval_head(s: Snapshot) -> str:
    if s.approval is None:
        return ""
    if s.approval.dry_run:
        badge, note = '<span class="ap-pill neutral">Dry run</span>', \
            "Approving publishes to a <code>dryrun://</code> address only. Nothing goes to Bluesky."
    else:
        badge, note = '<span class="ap-pill bad">Live</span>', "Approving publishes this post to Bluesky now."
    return (f'<div class="ap-dialog-head"><h2 id="approval-title">Approve this post?</h2>{badge}</div>'
            f'<p class="ap-dialog-note">{note}</p>')


def _approval_body(s: Snapshot, brand: str) -> str:
    if s.approval is None:
        return ""
    text = _draft_text(s.approval.prompt)
    over = len(text) > MAX_POST_CHARS
    scores = _SCORES_RE.findall(s.log)
    chips = ""
    if scores:
        names = ("voice", "clarity", "cta", "policy risk")
        chips = "".join(f'<span class="ap-score">{n} <b>{v}</b></span>' for n, v in zip(names, scores[-1]))
        chips = f'<div class="ap-scores"><span class="ap-label">Critic</span>{chips}</div>'
    return (
        f'<article class="ap-post"><header>{html.escape(brand)}</header>'
        f'<p>{html.escape(text)}</p>'
        f'<footer class="{"bad" if over else ""}">{len(text)} / {MAX_POST_CHARS}</footer></article>'
        f'{chips}'
        f'<p class="ap-hint">The critic has scored invented details 5/5 before. Check every time, date and claim '
        f'against the brief.</p>'
    )


def _plan_html(rationale: str, rows: list[list[str]]) -> str:
    if not rows:
        return f'<div class="ap-empty"><p>{html.escape(rationale)}</p></div>'
    body = "".join(
        f'<tr><td class="ap-num">{html.escape(day)}</td><td><span class="ap-topic">{html.escape(topic)}</span>'
        f'<span class="ap-id">{html.escape(post_id)}</span></td><td>{html.escape(goal)}</td>'
        f'<td><span class="ap-pill {_STATUS_TONE.get(status, "neutral")}">{html.escape(status.replace("_", " "))}'
        f'</span></td><td class="ap-note">{html.escape(note)}</td></tr>'
        for day, post_id, topic, goal, status, note in rows)
    return (f'<p class="ap-rationale">{html.escape(rationale)}</p>'
            f'<div class="ap-table-wrap"><table class="ap-table"><thead><tr><th>Day</th><th>Topic</th><th>Goal</th>'
            f'<th>Status</th><th>Latest note</th></tr></thead><tbody>{body}</tbody></table></div>')


def build(ctl: Controller) -> gr.Blocks:
    brand = _brand_name()
    with gr.Blocks(title="Autopilot", analytics_enabled=False) as demo:
        with gr.Row(elem_id="ap-topbar", equal_height=True):
            gr.HTML('<h1 class="ap-brand">Autopilot</h1>', padding=False, elem_classes="ap-shrink")
            state_html = gr.HTML(padding=False, elem_classes="ap-shrink")
            budget_html = gr.HTML(padding=False, elem_classes="ap-grow")
        budget_warn = gr.HTML(padding=False)

        with gr.Tab("Run"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=2, min_width=240, variant="panel", elem_classes="ap-card"):
                    gr.HTML('<h2>Next post</h2><p class="ap-muted">Measures earlier posts, writes and checks the '
                            'next post in the plan, then asks you before anything goes out.</p>', padding=False)
                    with gr.Row(elem_classes="ap-actions"):
                        live_btn = gr.Button("Run live", variant="primary", elem_id="run-live")
                        dry_btn = gr.Button("Dry run", variant="secondary", elem_id="run-dry")
                with gr.Column(scale=3, min_width=240, variant="panel", elem_classes="ap-card"):
                    gr.HTML('<h2>Your own topic</h2><p class="ap-muted">One post on a topic you choose, with the '
                            'same checks and approval.</p>', padding=False)
                    topic = gr.Dropdown(label="Topic", choices=[], value=None, allow_custom_value=True,
                                        info="Pick one from your plans, or type a new one")
                    with gr.Row():
                        angle = gr.Textbox(label="Angle (optional)", scale=3, min_width=160,
                                           placeholder="one concrete detail a beginner would notice")
                        goal = gr.Dropdown(label="Goal", choices=["awareness", "engagement", "click"],
                                           value="engagement", scale=1, min_width=160)
                    with gr.Row(elem_classes="ap-actions"):
                        topic_live_btn = gr.Button("Post live", variant="primary", elem_id="topic-live")
                        topic_dry_btn = gr.Button("Dry run", variant="secondary", elem_id="topic-dry")
            answer_note = gr.Markdown(elem_classes="ap-notice")
            log = gr.Textbox(label="Activity", lines=16, max_lines=16, autoscroll=True, interactive=False,
                             elem_classes="ap-log", placeholder="Nothing has run since the app opened.")

        with gr.Tab("Plan") as plan_tab:
            plan_html = gr.HTML(padding=False, elem_id="plan-table")
            with gr.Row(equal_height=False, elem_classes="ap-toolbar"):
                escalated = gr.Dropdown(label="Escalated posts", choices=[], scale=3,
                                        info="Only escalated posts can go back in the queue")
                requeue_btn = gr.Button("Requeue", variant="secondary", scale=0, elem_id="requeue")
                plan_btn = gr.Button("Plan next week now", variant="secondary", scale=0, elem_id="plan-now")
            gr.HTML('<p class="ap-muted">Plan now runs only when no post is waiting; otherwise it is refused before '
                    'any model call. Progress shows in the Run tab.</p>', padding=False)
            plan_note = gr.Markdown(elem_classes="ap-notice")

        with gr.Tab("Status") as status_tab:
            with gr.Column(variant="panel", elem_classes="ap-card"):
                gr.HTML("<h2>Requests</h2>", padding=False)
                quota_md = gr.Markdown()
                gr.HTML("<h2>Posting</h2>", padding=False)
                rate_md = gr.Markdown()
                gr.HTML("<h2>GitHub</h2>", padding=False)
                github_md = gr.Markdown()
                with gr.Row(elem_classes="ap-actions"):
                    refresh_btn = gr.Button("Refresh", variant="secondary", elem_id="refresh")
                    pull_btn = gr.Button("Pull from GitHub", variant="secondary", elem_id="pull")
                    save_btn = gr.Button("Save to GitHub", variant="primary", elem_id="save")
            status_note = gr.Markdown(elem_classes="ap-notice")

        # The two moments that must not be missed or mis-clicked get a real dialog: the scrim blocks the page
        # behind, and app.js moves focus to the safe choice and closes the confirm on Esc.
        with gr.Column(visible=False, elem_id="confirm-modal", elem_classes="ap-modal") as confirm:
            with gr.Column(elem_classes="ap-dialog"):
                gr.HTML('<div class="ap-dialog-head"><h2 id="confirm-title">Start a live run?</h2>'
                        '<span class="ap-pill bad">Live</span></div>', padding=False)
                confirm_md = gr.HTML(padding=False, elem_id="confirm-body")
                with gr.Row(elem_classes="ap-actions ap-end"):
                    cancel_btn = gr.Button("Cancel", variant="secondary", elem_id="confirm-cancel")
                    confirm_btn = gr.Button("Start live run", variant="primary", elem_id="confirm-yes")
        with gr.Column(visible=False, elem_id="approval-modal", elem_classes="ap-modal") as card:
            with gr.Column(elem_classes="ap-dialog"):
                approval_head = gr.HTML(padding=False, elem_id="approval-head")
                approval_body = gr.HTML(padding=False, elem_id="approval-body")
                with gr.Row(elem_classes="ap-actions ap-end"):
                    reject_btn = gr.Button("Reject", variant="stop", elem_id="approval-reject")
                    later_btn = gr.Button("Not now", variant="secondary", elem_id="approval-later")
                    approve_btn = gr.Button("Approve", variant="primary", elem_id="approval-approve")
                gr.HTML('<p class="ap-hint">Not now carries the post to the next run. Reject blocks it for good. '
                        'No answer in 15 minutes counts as Not now.</p>', padding=False)

        approval_id = gr.State(0)
        pending = gr.State("next")  # which live run the confirm dialog is for
        seen = gr.State(None)  # what this page last drew, so an unchanged tick sends nothing
        run_buttons = [live_btn, dry_btn, topic_live_btn, topic_dry_btn, plan_btn]

        def tick(last: Any) -> Any:
            s = ctl.snapshot()
            key = (s.running, s.what, s.dry_run, s.log, s.approval, s.exit_code)
            if key == last:
                return (gr.skip(),) * (9 + len(run_buttons))
            just_finished = last is not None and last[0] and not s.running
            return (_state_html(s), gr.update(visible=s.approval is not None), _approval_head(s),
                    _approval_body(s, brand), s.approval.id if s.approval else 0, s.log, key,
                    *(_budget_html(budget()) if just_finished else (gr.skip(), gr.skip())),
                    *(gr.update(interactive=not s.running) for _ in run_buttons))

        gr.Timer(1.0).tick(tick, inputs=seen, outputs=[state_html, card, approval_head, approval_body, approval_id,
                                                       log, seen, budget_html, budget_warn, *run_buttons], **_QUIET)
        # Counting reads every trace file, so the meter refreshes on load, when a run ends and every 30 s.
        demo.load(lambda: _budget_html(budget()), outputs=[budget_html, budget_warn], **_QUIET)
        gr.Timer(30.0).tick(lambda: _budget_html(budget()), outputs=[budget_html, budget_warn], **_QUIET)
        demo.load(lambda: gr.update(choices=topic_choices()), outputs=topic, **_QUIET)

        def ask_confirm(which: str, topic_text: str | None) -> tuple[Any, str, str, str]:
            if which == "topic" and not (topic_text or "").strip():
                return gr.update(visible=False), "Write a topic first.", which, ""
            body = _CONFIRM[which]
            if which == "topic":
                body = f'<p class="ap-dialog-topic">{html.escape((topic_text or "").strip())}</p>' + body
            return gr.update(visible=True), "", which, f'<div class="ap-dialog-note">{body}</div>'

        def confirmed(which: str, topic_text: str | None, angle_text: str, goal_value: str) -> tuple[Any, str]:
            if which == "topic":
                return gr.update(visible=False), ctl.start_topic(topic_text, angle_text, goal_value, dry_run=False)
            return gr.update(visible=False), ctl.start(dry_run=False)

        confirm_outputs = [confirm, answer_note, pending, confirm_md]
        live_btn.click(lambda t: ask_confirm("next", t), inputs=topic, outputs=confirm_outputs, **_PRIVATE)
        topic_live_btn.click(lambda t: ask_confirm("topic", t), inputs=topic, outputs=confirm_outputs, **_PRIVATE)
        cancel_btn.click(lambda: (gr.update(visible=False), "Live run cancelled."), outputs=[confirm, answer_note],
                         **_PRIVATE)
        confirm_btn.click(confirmed, inputs=[pending, topic, angle, goal], outputs=[confirm, answer_note], **_PRIVATE)
        dry_btn.click(lambda: (gr.update(visible=False), ctl.start(dry_run=True)), outputs=[confirm, answer_note],
                      **_PRIVATE)
        topic_dry_btn.click(lambda t, a, g: (gr.update(visible=False), ctl.start_topic(t, a, g, dry_run=True)),
                            inputs=[topic, angle, goal], outputs=[confirm, answer_note], **_PRIVATE)
        approve_btn.click(lambda i: ctl.answer(i, "approve"), inputs=approval_id, outputs=answer_note, **_PRIVATE)
        later_btn.click(lambda i: ctl.answer(i, "not_now"), inputs=approval_id, outputs=answer_note, **_PRIVATE)
        reject_btn.click(lambda i: ctl.answer(i, "reject"), inputs=approval_id, outputs=answer_note, **_PRIVATE)

        def load_plan() -> tuple[str, Any]:
            text, rows, ids = plan_rows()
            return _plan_html(text, rows), gr.update(choices=ids, value=ids[0] if ids else None)

        def requeue(post_id: str | None) -> tuple[str, str, Any]:
            note = ctl.requeue(post_id) if post_id else "Pick an escalated post first."
            return (note, *load_plan())

        plan_tab.select(load_plan, outputs=[plan_html, escalated], **_PRIVATE)
        requeue_btn.click(requeue, inputs=escalated, outputs=[plan_note, plan_html, escalated], **_PRIVATE)
        plan_btn.click(ctl.plan_now, outputs=plan_note, **_PRIVATE)

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

        status_outputs = [quota_md, rate_md, github_md]
        status_tab.select(load_status, outputs=status_outputs, **_PRIVATE)
        refresh_btn.click(load_status, outputs=status_outputs, **_PRIVATE)
        pull_btn.click(lambda: git_action("pull"), outputs=status_note, **_PRIVATE).then(
            load_status, outputs=status_outputs, **_PRIVATE)
        save_btn.click(lambda: git_action("save"), outputs=status_note, **_PRIVATE).then(
            load_status, outputs=status_outputs, **_PRIVATE)
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
                ssr_mode=False, mcp_server=False, quiet=True, theme=THEME, css=CSS, head=HEAD,
                footer_links=["settings"])
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
