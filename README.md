# Autopilot

An autonomous marketing agent for a fictional small business (Bramblewick Bakehouse, a sourdough bakery that teaches weekend classes). It plans a week of social posts, writes and critiques drafts, publishes to Bluesky, reads the engagement back, and feeds what it learned into the next plan.

It is a portfolio project about **AI engineering, not about marketing results**: the point is the harness around the models, and that every decision can be checked in a trace. It runs at **$0** on OpenRouter's free models and free hosting tiers.

**Live:** https://autopilot-kkazei.vercel.app: a public page about the project, and a private control panel (owner only) for approving posts, starting runs and reading traces.

## The rules, in plain words

These are enforced in code and covered by tests (see `CLAUDE.md` for the exact wording).

1. **Code, not the model, controls the flow.** A loop in `loops/` decides what happens next. An agent never decides to publish.
2. **One door to the outside world.** Only harness code can call the publish tool, and only after the draft is valid, passes the brand-safety checks and the rate cap (3 posts a day, 60 minutes apart), and a human has said yes.
3. **Everything is traced.** Every model call and tool call is written to a JSON trace, with secrets redacted.
4. **Model output is validated.** Each agent's reply must match a schema. If it is not valid JSON, the harness makes one repair attempt and then fails cleanly and logs it.
5. **The harness decides whether a draft passed.** The critic gives scores; the pass or fail is computed from them against a threshold, never taken from the model's say-so.
6. **No unbounded loops.** A draft gets at most 3 revisions, then goes to a human. Request budgets cap every run, and a hard cap of 45 model requests a day keeps it inside the free tier.
7. **Each role gets only the tools it needs.** The planner and analyst are read-only, the writer can only read the brand brief, and the critic gets no tools.

## How it fits together

```
planner -> writer -> critic -> (revise, up to 3x) -> harness checks -> human approval -> publish -> measure -> learning
   ^                                                                                                   |
   +---------------------------------------------------------------------------------------------------+
```

The agent system (Python):

- `agents/`: planner, writer, critic, analyst (prompts and output handling).
- `loops/`: the inner loop (write, critique, revise) and the outer loop (plan, post, measure, learn).
- `harness/`: schemas, trace, guardrails, the model client with its fallback chain, publishing, quota. This is where the rules above live. `harness/db_sync.py` pulls the state from Postgres before a run and pushes it back after, under a database lock, so the harness itself still works on plain files.
- `mcp_server/`: the tools (brand brief, learnings, metrics, publish, save learning) behind one MCP server, with per-role allowlists.
- `scripts/`: `run_outer.py` (the weekly loop), `run_post.py` (one post), `db_run.py` (the weekly loop against Postgres), `db_import.py`, `demo_bad_brief.py`.

The hosted app:

```
phone or desk ──> web/ (Next.js, Vercel) ──reads──> Neon Postgres (plans, posts, learnings, traces)
                        │                                   ^
                        └──actions──> backend/ (FastAPI, Render) ──runs the harness, pull/push──┘
GitHub Actions (daily) ──> scripts.db_run --measure-only ──pull/push──> Neon
```

- `web/`: the Next.js app. A public landing page at `/`, and the owner-only panel: **Control** (start a run, the approval card with hold-to-publish, a topic post form, Measure now), **Plan**, **Traces** (every run as a timeline, down to each model call), **Learnings** (each published post, its engagement and the lesson it taught). Sign in with GitHub or a password, both locked to one owner.
- `backend/`: a small FastAPI service around the same controller the old local app used. It only accepts requests carrying a shared secret, can only start the run kinds listed in `backend/app.py`, and cannot switch approval off.
- **Postgres (Neon) is the source of truth.** Every hosted run and the daily job pull from it and push back to it; the lock means two runs never overlap.

`docs/WEB_APP_PLAN.md` has the decisions and setup, `docs/DESIGN.md` the design system.

## Using it

**The web app** is the normal way. Approving a post, starting a dry run, planning next week, writing about a topic, measuring engagement now: all from Control, on a phone or a desk. Live posts always wait for you to hold Publish; ignoring a draft carries it forward, it never posts by default.

**The daily job** (`.github/workflows/run.yml`) runs `scripts.db_run --measure-only` once a day: it reads likes, reposts and replies on posts at least 2 hours old and saves a learning for each. It never writes drafts or publishes. **Measure now** in the web app runs the same thing on demand.

## Running it locally at $0

You need Python 3.11+ and a free [OpenRouter](https://openrouter.ai) key; Node 24 for the web app; for real posting, a Bluesky account with an app password.

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt     # Windows; use .venv/bin/python on Linux or macOS
copy .env.example .env     # then fill in the values; .env is git-ignored and secrets are never logged
```

Things that cost nothing and need no key:

```
python -m pytest -q                      # the Python suite, offline (models are mocked, sockets are blocked)
python -m scripts.demo_bad_brief         # replay the planted-bad-brief demo with scripted models (docs/demo/bad_brief.json)
cd web && npm ci && npm test             # the web app's tests; npm run typecheck and npm run build also need no secrets
```

Runs from a terminal should go through Postgres, so the web app, the rate cap and the daily job all see them:

```
python -m scripts.db_run --dry-run       # the weekly loop against the database; publishes to a dryrun:// address
python -m scripts.db_run --measure-only  # what the daily job does
```

`db_run` passes its arguments to `run_outer` and needs `DATABASE_URL`. It exits with 6 if a hosted run holds the lock, and 7 if the result could not be saved. A live run asks `Publish this post? [y/N]`, so run it in a real terminal. `run_post` and plain `run_outer` still work, but on the local `data/` files only: use them for experiments, not for posting.

Models are listed in `OPENROUTER_MODELS`; on a 429 or a timeout the client backs off and tries the next one. The free models are unstable (some have been retired, others rate-limit in bursts), so expect to adjust that list.

**The web app locally:** copy `web/.env.example` to `web/.env.local`, fill it (the table in `docs/WEB_APP_PLAN.md` says where each value comes from), then `cd web && npm run dev`. GitHub sign-in needs a separate OAuth app whose callback is `http://localhost:3000`; the password sign-in works anywhere once `AUTH_PASSWORD_HASH` is set (`node scripts/hash-password.mjs`).

**Hermes writer runtime (opt-in).** By default every agent calls OpenRouter straight from the harness. With `AUTOPILOT_WRITER_RUNTIME=hermes` (and the `hermes` CLI installed), the writer's first call of each attempt runs through [Hermes Agent](https://github.com/NousResearch/hermes-agent) behind a harness-owned LLM proxy that holds the key; a cross-check of the proxy, Hermes's output and the tool call log fails closed, and anything it cannot trust falls back to the direct chain. Repairs, the critic and the other roles always run direct. The hosted backend and the daily job run direct. One live run so far: Hermes answered and the cross-check passed, but its draft was over the length limit, so the post was written by the harness's direct repair.

**Retired:** the local Gradio app with its Save-to-GitHub data PRs, and the static dashboard. Both worked on the `data/` files in git, which stopped updating when Neon became the source of truth on Oct 28. Their last version is archived in the [local-app-final](https://github.com/kkazei/autopilot/releases/tag/local-app-final) release. `ui/controller.py` stays; the backend uses it.

## What is proven, and what is partial

**Proven for real**
- 5 live posts on Bluesky (Oct 22 to Oct 28), each human-approved, with full traces. The latest was approved from the web app with hold-to-publish. Four more drafts were declined at the approval prompt (an invented class time, invented crust details, invented scarcity, and one claim about customers), and their traces are kept too.
- The learn loop on real data: 6 learnings across 4 measured posts, and a real planner cited a learning in a plan that passed the harness's check (`data/evidence/stage_f`). Posts with too little engagement are saved as "not enough data" and read again on later runs; the two oldest got their learnings that way on Oct 26 (`run_20261026_101942_a284db`). **All of the engagement is from people the builder knows, not an organic audience.**
- The scheduled run fired on its own every day from Oct 24 to Oct 28 (hours after its 06:17 UTC slot each time) and succeeded. It only measures and can never publish. CI runs the Python and web tests on every push and pull request.
- The hosted path end to end: a dry run started from the web app on Render, pulled from Neon, ran plan, write, critique and every guardrail, waited for approval in the browser, and pushed its trace back (`run_20261028_140054_e50c59`).
- A Bluesky timeout after sending: the pending row blocked a retry, the account's server showed no post, and the row was settled by hand without editing history (`run_20261025_103042_bfa092`).
- On real models, from real traces: JSON/length repair (it succeeded several times and failed cleanly twice), 429 backoff and fallback down the chain, and guardrails before every publish. The rate cap blocked a run before any model call on the real harness (`data/evidence/stage_d`).
- The harness's failure handling (revision cap, JSON repair, rate cap, banned phrase, 429 fallback, prompt injection, publish ordering, the database lock and sync) in automated tests: 572 Python tests that run offline (2 more need a separate test database) and 23 web tests.

**Partial or not proven yet**
- **The critic is the weak link.** Calibration on 10 hand-scored drafts: it agreed on 6 of 10 and was too lenient on d03, d06, d08 and d10. One rubric change raised that to 7 of 10, which is one draft and within run-to-run noise, measured on the same 10 drafts. It is still lenient on d03, d06 and d10. On real drafts it scored an invented class time, invented crust details, a claim about customers and urgency pressure 5 out of 5, and it noticed invented scarcity ("a few spots remain") but still passed it at 4. Human approval caught each one, which is why approval stays mandatory.
- **No organic engagement.** Every learning with signal comes from likes and reposts by people the builder knows, and the one plan that cited a learning used it shallowly. The analyst's wording can also go further than three likes support: one learning says a post "resonated modestly with a niche audience".
- **The free writer often overshoots the 300-character limit.** On Oct 25, 4 of 8 one-shot repairs failed. The repair now aims at 240 (PR #17); that is unproven on a real model.
- **The planner's angle was a source of invented claims** (stage B). The prompts now treat the angle as a focus, not as a fact (PR #15). That is tested offline only. The calibration numbers above were measured on the critic prompt before that change.
- **Failure forcing on a real model is partial** (`data/evidence/stage_d/README.md`). Prompt injection was resisted, but the run stopped at a length repair before the critic. The banned phrase was not forced: the writer avoided it, and approval caught the urgency instead. The revision cap was not forced: the free critic is too lenient to fail three times on demand.
- **Render's free tier sleeps** after 15 idle minutes; the first action after that waits about a minute while it wakes (the app says so and disables the run buttons until it answers).
- **The 50-requests-a-day free limit is assumed**, not confirmed for this account. The free model pool is unstable, and poolside's `laguna` id expires on Oct 31.

## What it is autonomous at, and what is next

It plans the week, writes and revises drafts, checks them, measures the posts and learns from them on its own; the
daily job measures and learns with nobody at the keyboard. **It does not publish on its own.** A human approves every
post, from the web app, because the critic missed an invented class time and urgency pressure on real drafts.

Next steps, in order:
1. **Replace poolside's `laguna` model id** before it expires on Oct 31, and recalibrate the critic on fresh drafts.
2. **A code check for times, prices and numbers that are not in the brief.** It would have caught the invented class
   time without relying on the critic.
3. **Check the account's server automatically after a publish timeout**, instead of leaving "outcome unknown" for a human to settle by hand.

Details and decisions: `docs/HANDOFF.md` (the build log up to Oct 26) and `docs/WEB_APP_PLAN.md` (the web app). Deploying: `docs/DEPLOY.md`.
