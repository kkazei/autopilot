# Autopilot

An autonomous marketing agent for a fictional small business (Bramblewick Bakehouse, a sourdough bakery that teaches weekend classes). It plans a week of social posts, writes and critiques drafts, publishes to Bluesky, reads the engagement back, and feeds what it learned into the next plan.

It is a portfolio project about **AI engineering, not about marketing results**: the point is the harness around the models, and that every decision can be checked in a trace. It runs at **$0** on OpenRouter's free models.

## The rules, in plain words

These are enforced in code and covered by tests (see `CLAUDE.md` for the exact wording).

1. **Code, not the model, controls the flow.** A loop in `loops/` decides what happens next. An agent never decides to publish.
2. **One door to the outside world.** Only harness code can call the publish tool, and only after the draft is valid, passes the brand-safety checks and the rate cap (3 posts a day, 60 minutes apart), and a human has said yes.
3. **Everything is traced.** Every model call and tool call is written to a JSON trace in `data/runs/`, with secrets redacted.
4. **Model output is validated.** Each agent's reply must match a schema. If it is not valid JSON, the harness makes one repair attempt and then fails cleanly and logs it.
5. **The harness decides whether a draft passed.** The critic gives scores; the pass or fail is computed from them against a threshold, never taken from the model's say-so.
6. **No unbounded loops.** A draft gets at most 3 revisions, then goes to a human. Request budgets cap every run.
7. **Each role gets only the tools it needs.** The planner and analyst are read-only, the writer can only read the brand brief, and the critic gets no tools.

## How it fits together

```
planner -> writer -> critic -> (revise, up to 3x) -> harness checks -> human approval -> publish -> measure -> learning
   ^                                                                                                   |
   +---------------------------------------------------------------------------------------------------+
```

- `agents/`: planner, writer, critic, analyst (prompts and output handling).
- `loops/`: the inner loop (write, critique, revise) and the outer loop (plan, post, measure, learn).
- `harness/`: schemas, trace, guardrails, the model client with its fallback chain, publishing, quota. This is where the rules above live.
- `mcp_server/`: the tools (brand brief, learnings, metrics, publish, save learning) behind one MCP server, with per-role allowlists.
- `scripts/`: `run_post.py` (one post), `run_outer.py` (the weekly loop), `export_dashboard_data.py`, `demo_bad_brief.py`.
- `dashboard/`: a static, read-only one-page dashboard (totals, posts, learnings, runs); a post, a run's trace and the known limits open in dialogs. `evals/` and `tests/`: the tests.

## Running it at $0

You need Python 3.11+, a free [OpenRouter](https://openrouter.ai) key and, only for real posting, a Bluesky account with an app password.

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt     # Windows; use .venv/bin/python on Linux or macOS
copy .env.example .env     # then fill in the values; .env is git-ignored and secrets are never logged
```

Things that cost nothing and need no key:

```
python -m pytest -q                      # the whole test suite, offline (models are mocked)
python -m scripts.demo_bad_brief         # replay the planted-bad-brief demo with scripted models (docs/demo/bad_brief.json)
python -m scripts.export_dashboard_data  # build dashboard/data.json; then open dashboard/index.html in a browser
```

Things that call the real free models (they spend the free daily quota, about 2 to 9 requests for one post):

```
python -m scripts.run_post --topic "<a real, specific topic>" --goal click --dry-run   # publishes to a dryrun:// address
python -m scripts.run_post --topic "<a real, specific topic>" --goal click             # asks you before posting
```

Run these in a real terminal: the approval prompt needs a keyboard. Models are listed in `OPENROUTER_MODELS`; on a 429 or a timeout the client backs off and tries the next one. The free models are unstable (some have been retired, others rate-limit in bursts), so expect to adjust that list.

**The local app (optional).** The same weekly run, with approval buttons instead of the terminal prompt:

```
.venv/Scripts/python.exe -m pip install -r requirements-ui.txt   # gradio; CI and the scheduled run never need it
Autopilot.bat                                                    # or: python -m ui.app --open
```

It serves on 127.0.0.1 only (no share link, analytics off, Gradio's client API off) and opens in its own Edge window; closing the console window stops it. **Run** starts a dry run, or a live run after a second click, of the next due post or of a post on your own topic (the same as `run_post`), and shows the draft with Approve, Not now (carried forward to the next run) and Reject (blocked for good); no answer within 15 minutes counts as Not now. **Plan** shows the week, requeues escalated posts, and plans next week ahead of time (`run_outer --plan-only`, refused while any post is waiting). **Status** shows the day's request count and the rate cap, pulls from GitHub (fast-forward, on master only), and **Save to GitHub** opens a PR with only `data/` on a new `data/app-...` branch; it never pushes to master. The terminal commands keep working exactly as before.

**Hermes writer runtime (opt-in).** By default every agent calls OpenRouter straight from the harness. With `AUTOPILOT_WRITER_RUNTIME=hermes` (and the `hermes` CLI installed), the writer's first call of each attempt runs through [Hermes Agent](https://github.com/NousResearch/hermes-agent) behind a harness-owned LLM proxy that holds the key; a cross-check of the proxy, Hermes's output and the tool call log fails closed, and anything it cannot trust falls back to the direct chain. Repairs, the critic and the other roles always run direct. One live run so far: Hermes answered and the cross-check passed, but its draft was over the length limit, so the post was written by the harness's direct repair.

## What is proven, and what is partial

**Proven for real**
- 3 live posts on Bluesky, each human-approved, with full traces. Four more drafts were declined at the approval prompt (an invented class time, invented crust details, invented scarcity, and one claim about customers), and their traces are kept too.
- The learn loop on real data: a live post was measured (4 likes, **from people the builder knows, not an organic audience**), the analyst saved a learning, and a real planner cited it in a plan that passed the harness's check (`data/evidence/stage_f`). The two earlier posts had zero engagement when first read, so they were saved as "not enough data"; they were read again on Oct 26 (2 likes and 1 repost, 3 likes and 1 repost; all from people the builder knows) and the analyst saved a learning for each (`run_20261026_101942_a284db`). That second read is the re-measuring step added in PR #26.
- The scheduled GitHub run fired on its own on Oct 24 and Oct 25 (hours after its 06:17 UTC slot each time) and succeeded. It only measures and can never publish. Its data push rebuilds the dashboard with nobody involved. CI runs the tests on every pull request.
- The planner and the write-and-critique half of the outer loop ran on real free models, as a dry run (plan, draft, a length repair, critique, all guardrails, a `dryrun://` publish).
- A Bluesky timeout after sending: the pending row blocked a retry, the account's server showed no post, and the row was settled by hand without editing history (`run_20261025_103042_bfa092`).
- On real models, from real traces: JSON/length repair (it succeeded several times and failed cleanly twice), 429 backoff and fallback down the chain, and guardrails before every publish. The rate cap blocked a run before any model call on the real harness (`data/evidence/stage_d`).
- The harness's failure handling (revision cap, JSON repair, rate cap, banned phrase, 429 fallback, prompt injection, publish ordering) in automated tests.
- The dashboard is live at https://autopilot.jirroaeron.workers.dev/ and rebuilds itself on every push to `master` (Cloudflare Workers Builds, $0; see `docs/DEPLOY.md`).

**Partial or not proven yet**
- **The critic is the weak link.** Calibration on 10 hand-scored drafts: it agreed on 6 of 10 and was too lenient on d03, d06, d08 and d10. One rubric change raised that to 7 of 10, which is one draft and within run-to-run noise, measured on the same 10 drafts. It is still lenient on d03, d06 and d10. On real drafts it scored an invented class time, invented crust details, a claim about customers and urgency pressure 5 out of 5, and it noticed invented scarcity ("a few spots remain") but still passed it at 4. Human approval caught each one, which is why approval stays mandatory.
- **No organic engagement.** Every learning with signal comes from likes and reposts by people the builder knows, and the one plan that cited a learning used it shallowly. That plan was shown once, with the planner alone, after a first attempt failed on free-model errors. The analyst's wording can also go further than three likes support: one learning says a post "resonated modestly with a niche audience".
- **The free writer often overshoots the 300-character limit.** On Oct 25, 4 of 8 one-shot repairs failed. The repair now aims at 240 (PR #17); that is unproven on a real model.
- **The planner's angle was a source of invented claims** (stage B). The prompts now treat the angle as a focus, not as a fact (PR #15). That is tested offline only. The calibration numbers above were measured on the critic prompt before that change.
- **Failure forcing on a real model is partial** (`data/evidence/stage_d/README.md`). Prompt injection was resisted, but the run stopped at a length repair before the critic. The banned phrase was not forced: the writer avoided it, and approval caught the urgency instead. The revision cap was not forced: the free critic is too lenient to fail three times on demand.
- **The scheduled run has fired twice**, hours late each time. That is still thin evidence for unattended running.
- **The 50-requests-a-day free limit is assumed**, not confirmed for this account. The free model pool is unstable, and poolside's `laguna` id expires on Oct 31.

## What it is autonomous at, and what is next

It plans the week, writes and revises drafts, checks them, measures the posts and learns from them on its own; the
scheduled GitHub run measures and learns every day with nobody at the keyboard. **It does not publish on its own.**
A human approves every post, because the critic missed an invented class time and urgency pressure on real drafts.

Next steps, in order:
1. **A draft queue with a one-click approval page.** The scheduled run would write each day's post and queue it; a
   small local page would show the draft and the critic's reasons with Approve and Decline buttons, which call the
   same harness checks as today's terminal prompt. Posting gets close to autonomous while the human check stays.
2. **A code check for times, prices and numbers that are not in the brief.** It would have caught the invented class
   time without relying on the critic.
3. **Check the account's server automatically after a publish timeout**, instead of leaving "outcome unknown" for a human to settle by hand.
4. **Replace poolside's `laguna` model id** before it expires on Oct 31, and recalibrate the critic on fresh drafts.

Details and decisions: `docs/HANDOFF.md`. To see it in action: the dashboard, and `python -m scripts.demo_bad_brief`. Deploying the workflow and the dashboard: `docs/DEPLOY.md`.
