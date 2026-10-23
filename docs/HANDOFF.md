# Autopilot handoff, updated 2026-10-23 mid-day (Day 1 complete, Day 2 in progress)

Status key: `[x]` done, `[~]` partly done, `[ ]` not started, `[-]` deferred by decision.

## 1. Sources of truth
- **Repo:** `C:\Users\jirro\orca\projects\autopilot` (Windows 11, PowerShell plus Git Bash).
  - Remote: `https://github.com/kkazei/autopilot` (private).
  - Main branch `master`; all current work is on `feat/hermes-runtime`. No PR is open.
- **Build plan (authoritative):** `C:\Users\jirro\Downloads\Autopilot 3-Day Build Plan and Claude Code Prompts.pdf` (30 pages).
  - It holds the repo layout, the data contracts, prompts D1-S to D3-C, the critic rubric, the failure table, deployment and the demo script.
  - The Read tool can't render it on this machine; use `pdftotext -layout` (available in Git Bash).
- **`CLAUDE.md`:** the project rules. Paste artifacts were removed in `d10bb10`, and it now also says no attribution trailers.
- **`docs/ISSUES_LOG.md`, local only, not in git:** what went wrong and how it was resolved (for the interview). It is excluded through `.git/info/exclude`, so it stays on the user's disk only. Keep it current. References below say "local ISSUES_LOG".

## 2. Where we are (one-screen summary)
- **Status: Day 1 complete; Day 2 in progress. The outer loop (f) is built and committed but has never run against a real model.**
- **Day:** Day 2 is Fri Oct 23. The schedule runs Oct 22-24.
- **Live posts so far (2):**
  - `run_20261022_092913_bde119` (Oct 22, 09:29 UTC), `at://did:plc:ogjf457tkxqfttvdsfbvjl7p/app.bsky.feed.post/3myhe2q5j432a`.
  - `run_20261023_071243_174bcb` (Oct 23, 07:13 UTC), a second Saturday-sourdough post.
  - Both were human-approved. Records are in `data/approved.jsonl`.
- **Three runs on Oct 23 ended without a post** (traces committed as evidence): `d77bec` (placeholder topic; the writer's draft was 312 characters and the repair failed), `ee5488` (the approval prompt had no stdin because the run used the `!` prefix; the draft had also drifted off the topic), `c48e24` (8-attempt writer budget used up; minimax `:free` retired, poolside and gemma 429, cohere truncated).
- **Built:** P1 harness core, `harness/llm.py`, the live Bluesky client, log-before-publish, writer, critic, inner loop, `harness/publish.py`, `scripts/run_post.py`, and (Day 2) link facets, the critic fact-check, topic-fit rules, dead-model skip, and the whole outer loop: `harness/measure.py`, `agents/analyst.py`, `agents/planner.py`, `harness/plan_state.py`, `harness/quota.py`, `loops/outer.py`, `scripts/run_outer.py`.
- **Tests:** 360 passing offline on Python 3.14.8 (`.venv`) and 3.11.16 (`.venv311`) (253 at the start of today).
- **Latest live attempt (Oct 23, 09:00 UTC, `run_20261023_090036_b0e71e`):** the topic fix worked (the draft was about the free sample loaf, passed on attempt 1, and the human declined it at the approval prompt, so nothing was published). Poolside 429'd then truncated; flint wrote the draft using 3,513 of its 4,096 tokens; poolside scored it 5/5. The draft was weak: it opened with the topic text word for word and said "Beginners often notice the crust and crumb first", an unsupported customer claim the critic missed. Both were addressed offline in `ca7af10` and are unproven on a real model. The repo's quota count undercounts by the 4 probe requests that went to a scratch folder: about 42 of 50 used by 09:05 UTC.
- **Day 2 progress:** (a) link facets (`3935a10`); (b) critic fact-check (`3d96fe7`); (c) banned variants and (d) quota decision done earlier; topic drift fixed offline (`ffe39e1`); dead-model skip (`fc3abf0`); (f) outer loop committed in four chunks (`c26f11f`, `5b60760`, `975da5f`, `fa24b3e`) plus data (`d03dc07`). D2-C failure tests done (`d447a21`); D2-D workflow files and `docs/DEPLOY.md` written and checked locally (`f9dff75`, never run on GitHub). Still open: (e) more live posts, D2-B calibration, first real `run_outer`, merging to `master` so the workflows can run, P2.
- **Model chain (`.env`, changed today):** `poolside/laguna-s-2.1:free, recursive/flint-v1.0:free, google/gemma-4-31b-it:free, cohere/north-mini-code:free`. See decision 4.9 for why.
- **Quota:** the repo's own count was 34 of 50 requests in the last 24 hours at about 08:50 UTC on Oct 23 (`quota.run_cap` counts failed attempts too, so it likely overstates). Do at most one more live post today.
- **Known gaps remaining:**
  - Whether a real free model obeys the fact-check and topic-fit rules (critic) and the topic rule (writer) is unproven until a live run or D2-B calibration.
  - The outer loop has only run against `MockLLM`; its first real run will also be the first real planner and analyst call.
  - The critic passed a customer claim ("Beginners often notice the crust and crumb first") in `b0e71e`; the critic and writer prompts were tightened offline (`ca7af10`) and are unproven live. Flint spends about 3,500 tokens on a short post, so it is close to the 4,096-token truncation limit.
  - The 50 requests/day limit is unconfirmed for this account (issue 18; decided to stay at $0).
  - The GitHub schedule only measures (decision 4.11); it can never publish. The workflows have not run on GitHub and only work from `master`.
  - `run_post` still enforces "no `--no-approve` without `--dry-run`" only in its CLI; `run_outer` now enforces it inside `run_outer()` too.
- See the Day 2 checklist in section 5.

## 3. Git state
| Commit | What | Pushed |
|---|---|---|
| `ed5877a`, `fb5f356` | Initial commit, project init (CLAUDE.md, .env.example, data/.gitkeep) | yes (`master`) |
| `f774123` | feat: Hermes spike and P1 harness core (schemas, trace, guardrails, MCP server) | yes (`feat/hermes-runtime`) |
| `d10bb10` | docs: remove paste artifacts from CLAUDE.md and add no-attribution rule | yes |
| `cd0e1f2` | feat: llm fallback chain, live Bluesky client, log-before-publish | yes |
| `7ee2e88` | feat: writer, critic, inner loop, single publish path and run_post | yes |
| `2b9d1d8` | fix: handle truncated reasoning-model replies and tighten repair prompt | yes |
| (end of Day 1) | docs+data: first live post, traces and handoff (this file, `approved.jsonl`, the live and failed run traces) | yes |
| `e48066d` | fix: harden publish path, banned-phrase matching and loop failure handling after independent review (R1-R10) | yes |
| `3935a10` | feat: link facets with UTF-8 byte offsets and hardened URL boundary detection (Day 2 item (a)) | yes |
| `3d96fe7` | feat: critic checks claims against the brief and planned post (Day 2 item (b)) | no |
| `c70e643` | docs: record decision to stay at $0 free tier | no |
| `ffe39e1` | fix: keep drafts on the planned topic (writer `TOPIC_RULE`, critic `TOPIC_FIT`) | no |
| `fc3abf0` | fix: skip a model that returns 404 for the rest of the run | no |
| `c26f11f` | feat: run-wide request budget, long-lived lock option and tool results as data | no |
| `5b60760` | feat: measure published posts and save a learning for each | no |
| `975da5f` | feat: weekly planner, plan state and daily request guard | no |
| `fa24b3e` | feat: outer loop and run_outer script | no |
| `d03dc07` | data: today's live post and run traces | yes |
| `8c36255` | docs: update handoff for Day 2 progress, model chain and outer loop | yes |
| `3f4d25a` | fix: keep the head and the tail of long trace summaries (issue 31) | no |
| `ca7af10` | fix: stop the writer echoing the topic and the critic missing claims about customers | no |
| `43b7545` | docs: handoff for issue 31 fix, prompt tightening and the b0e71e run | no |
| `d447a21` | test: end-to-end failure-handling tests for the seven D2-C cases (`evals/test_failure_handling.py`) | no |
| `f9dff75` | ci: GitHub Actions workflows and deploy doc (D2-D) | no |

- Every commit is authored by the user's identity `z <jirroaeron@gmail.com>`, with no trailers.
- **Local only, not in git:** `docs/ISSUES_LOG.md` (listed in `.git/info/exclude`).
- **Untracked on purpose:** `data/runs/run_20261022_080056_bb7b95.json`, a P1 sample dry-run trace with no LLM calls. Keep it out of git so it never shows on the dashboard.
- **Scratch work from today lives outside the repo:** the model probe script and its traces are in the session scratchpad, not in `data/`.
- **Git-ignored:** `.env`, `.venv/`, `.venv311/`, `data/runtime/` (the MCP call log), `.hermes_spike/`, `vendor/hermes-agent/`.

## 4. User decisions (settled: do not re-ask)
1. **Runtime:** Tier A. Hermes runs all four roles behind a harness-owned local LLM proxy. The D1-S suggestion to drop Hermes was rejected.
2. **Order of work: live path first.**
   - Build P2 (the Hermes runtime) only **after** one approved live post (now done).
   - Time-box P2 to about **2 hours**. If it overruns, fall back to calling OpenRouter directly (the PDF's own fallback).
3. **Rate cap vs outer loop:** process **only the posts that can publish today**. Do not write or critique drafts that the cap will block; carry them forward to later runs.
4. **The five earlier approvals (all approved):**
   - Publish records live in `data/approved.jsonl`, which `check_rate_cap` reads.
   - Dry-run `get_metrics` returns zeros for `dryrun://` URIs; a fixture override is allowed in tests only.
   - Test layout: `evals/test_harness.py` for harness and failure tests, `tests/` for MCP, runtime and loop tests.
   - Upstream-attempt budgets 12/8/4/12 (planner/writer/critic/analyst), configurable.
   - Brand brief "Bramblewick Bakehouse", with `cta_url: https://example.com/bramblewick/classes`.
5. **Commits and PRs:** never add a co-author, "Generated with" or any other attribution trailer. Use the user's exact message when one is given.
6. **Committing:** commit only when the user says so and only what they name. The user decides what goes in git.
7. **Approval flag (D1-D):** `scripts/run_post.py` takes `--approve/--no-approve`, default on. `--no-approve` is refused unless `--dry-run` is also set, so no live post goes out without a human. This must be revisited deliberately for the Day 2 cron (D2-D), and not loosened before then.
8. **Writer brief (D1-D):** the brief goes in the writer prompt, and `get_brand_brief` is also offered through the allowlist-checked dispatcher in `agents/base.py` (Option A). Per-call upstream-attempt budgets stay on in `llm.py`.
9. **Model chain (changed Oct 23):** `OPENROUTER_MODELS` = poolside, flint, gemma-4-31b, cohere (all `:free`), in that order (cohere last because it truncates at 4,096 tokens).
   - **minimax `:free` is retired** (HTTP 404, "free launch period ended Oct 22"); it was removed from the chain and is gone from OpenRouter's list.
   - **Probed Oct 23 with one tool call each:** `recursive/flint-v1.0:free` OK on the first turn only (a full draft and critique are unproven); `nvidia/nemotron-3-super-120b-a12b:free` 404 (NVIDIA backend not found, like the earlier nemotron drop); `google/gemma-4-26b-a4b-it:free` and `xingchen-agi/xing4.0-29b-a4b:free` 429 (not tested further; gemma-26b shares Google's pool with gemma-31b).
   - **poolside's `laguna` ids carry an expiry of 2026-10-31.** Replace it before the cron runs past that date.
   - nemotron (404) and inkling (403) were dropped earlier, on Day 1.
   - `harness/llm.py` now skips a model that returned 404 for the rest of that client's life (one run), at the cost of one wasted slot per dead model per run until its id is removed.
10. **Truncation fix:** `max_tokens` 4,096; `finish_reason=length` moves to the next model; OpenRouter's `reasoning` setting deliberately not used.
11. **Cron posting (decided Oct 23):** the scheduled GitHub run only measures (`scripts.run_outer --measure-only`). Live posts stay local with human approval on, because a runner cannot answer the approval prompt. This settles the 4.7 revisit for D2-D without loosening it. Rejected: a cron that posts with approval off, and a pre-approved drafts queue (new code, not Day 2). A manual `dry_run` run does the whole loop without publishing.

## 5. Task list
### Day 1 (done)
- [x] **1. Commit the work** (`f774123`).
- [x] **2. Docs cleanup** (`d10bb10`; this handoff).
- [x] **3. Probe every model with one real tool call.** minimax, poolside and cohere pass; gemma 429 (kept last); nemotron 404 and inkling 403 dropped.
- [x] **4. `harness/llm.py` and the real Bluesky client** (`cd0e1f2`), plus D1-D (`7ee2e88`) and the truncation fix (`2b9d1d8`). Throwaway credential post made, read on the PDS and deleted. Python 3.11 venv in `.venv311`.
- [x] **5. One live post end to end with human approval on** (`run_20261022_092913_bde119`). The first live attempt (`run_20261022_092011_d8f068`) failed cleanly on a truncated reply; that trace is committed as evidence (local ISSUES_LOG 7.2, not in git).
- [x] Reported both gaps before step 5: `check_banned` variants (issue 17) and the free-tier limit (issue 18).

### Day 2 start checklist (in this order)
- [x] **(a) Link facets** for URLs in `mcp_server/bluesky.py` (local ISSUES_LOG 4.2, not in git), committed as `3935a10`.
  - UTF-8 byte offsets; tests cover multi-byte text before, between and around URLs, plus a seeded property test (300 random posts) and a facet-build failure test. 248 tests pass on both interpreters; 11 mutation checks all killed.
  - An independent verification pass found and fixed 7 URL-boundary defects: curly quotes, non-ASCII punctuation (`…`, `—`, `。`), `<>`, balanced `)` or `]` (Wikipedia style), uppercase scheme, hostless matches (`https://...`), and a glued combining accent.
  - **Accepted trade-offs:** a URL with a non-ASCII path (like `/café`) is not linked at all, rather than linked half-way; bare domains without `http(s)://` are not linked.
  - **Live check passed** (Oct 22): one test post through `bluesky.post()`. The PDS record had exactly one `#link` facet at bytes 37-67 slicing to the URL, offsets differing from the character index (33), and the AppView showed the facet. The post was deleted and confirmed `RecordNotFound`. It bypassed the harness, so it is not in `approved.jsonl` and does not count toward the rate cap.
  - The dry run could not exercise the facet code (dry runs never reach `bluesky.post`), and `--dry-run` still calls OpenRouter, so it was run in-process with a scripted LLM.
- [x] **(b) Critic fix** (local ISSUES_LOG 7.4, not in git), committed as `3d96fe7`.
  - `agents/critic.py`: the critic gets the same `planned_post` data block as the writer (goal inside it), a `FACT_CHECK` rule in the system prompt and a matching rubric line. A factual claim (sensory and craft detail included) not in the brief or the planned post caps `policy_risk` at 3, and the reason must quote the claim. `loops/inner.py`, the writer and the harness are unchanged; `passed` is still computed by the harness (rule 5).
  - 5 tests added to `tests/test_inner_loop.py`; 253 pass on both interpreters; 7 mutation checks all killed; an in-process dry run replayed the yogurt draft (attempt 1 flagged, attempt 2 passed).
  - **Limits:** offline tests cannot show a free model obeys the rule (D2-B calibration or a live probe decides that; the live probe was skipped on purpose to save quota); the cap only blocks at `--min-score` 4 or 5; over-flagging of harmless generic detail is unmeasured (count revisions per post in D2-B).
- [x] **(c) `check_banned` variants** (issue 17): done early, as review item 27 (inflections, spaced/dotted letters, no-space forms, `banned_variants` in the brief).
- [x] **(d) Quota decision** (issue 18): **decided Oct 23: stay at $0** (the user's goal is a free build to demo AI engineering). Ration the 50 requests/day: spread calibration over Day 2 and 3; buying credits is only a fallback if the user chooses it later. The 50/day limit is assumed from OpenRouter's docs and not yet confirmed for this account (a read-only check needs the user's approval).
- [~] **(e) Start posting early** with `scripts/run_post.py` (live, approval on) to build real engagement data. The 60-minute gap means 3-5 posts take 3+ hours of wall time. **2 live posts so far** (Oct 22 and Oct 23 07:13 UTC). Run it in a real terminal, never with the `!` prefix (no stdin, so approval is blocked): `.venv311/Scripts/python.exe -m scripts.run_post --topic "<a real, specific topic>" --goal click`. Never run it with a placeholder topic: "your topic here" was posted to the writer as the real topic once.
- [~] **(f) D2-A:** metrics, analyst, learnings, planner, outer loop (and issue 16, read-after-post). **Code complete and committed offline (343 tests); never run against a real model.**
  - `--dry-run` still makes real planner and writer calls, so it costs quota.
  - **Review of this code (Oct 23):** no architecture-rule violations. Two findings fixed with tests and mutation checks: the planner now cites only learnings with signal (while every learning is "not enough data" no citation is required), and `run_outer()` itself refuses approval-off for a live run.
  - **Design note:** with approval mandatory, an unattended run writes a draft nobody can approve, so the post is carried forward and the requests are wasted (D2-D, decision 4.7).
  - The first real outer run is also the first real planner and analyst call; expect to find prompt problems.
- [~] **(g) D2-B, D2-C, D2-D:**
  - **D2-B** critic calibration: not started (it is the biggest quota spender; do it once the quota frees up).
  - **D2-C** failure tests: **done** (`d447a21`, 12 tests, mutation-checked; no code bugs surfaced).
  - **D2-D** deploy: **files written, never run on GitHub** (`f9dff75`). Needs the workflows merged to `master` and the four secrets added (`docs/DEPLOY.md`).
- **Note:** the approval flag (decision 4.7) stays mandatory; decision 4.11 settles the cron as measure-only.

## 6. PDF checklist with current status

### Step 0: setup
- [x] Git and Python 3.11+ (local Python is 3.14.8; the target and CI are 3.11)
- [x] Orca and Claude Code running
- [x] GitHub repo `autopilot` created and cloned (`kkazei/autopilot`)
- [x] `.venv` and `.gitignore` (`.env`, `.venv/`, `__pycache__/`, `vendor/hermes-agent/`, plus `.hermes_spike/`, `data/runtime/`)
- [x] `.env.example` with `OPENROUTER_API_KEY`, `OPENROUTER_MODELS`, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`; copied to `.env`
- [x] `CLAUDE.md` in the repo root, committed and pushed
- [x] OpenRouter account and key, in `.env`
- [x] `data/.gitkeep`

### Day 1 (Thu Oct 22): foundation
Goal: one approved post live on Bluesky, full trace saved, harness tests passing.

**Block 1: Hermes spike**
- [x] Claude Code runs in Orca
- [x] Live free-model list checked and 4 tool-calling models picked (minimax, poolside, cohere proven; gemma kept last)
- [x] Hermes cloned into `vendor/hermes-agent/` (pinned to `1af97a3f31`, never modified); native install v0.21.4
- [x] Hermes called a tool on the stub MCP server (`mcp_server/stub_server.py`, `scripts/hermes_spike.py`)
- [x] Decision made: Hermes per role (Tier A)

**Block 2: accounts and brief**
- [x] Bluesky test account and app password (user; both env vars set in `.env`)
- [x] Post once from a throwaway script to prove the credentials work (posted, confirmed on the PDS, deleted)
- [x] `data/brand_brief.json` (Bramblewick Bakehouse)

**Block 3: parallel build (D1-A, D1-B, D1-C)**
- [x] **D1-A MCP server** (`mcp_server/server.py`): all 5 tools, DRY_RUN, 300-character limit, call log with receipts, per-role allowlists, harness-only `publish_post` and `save_learning` behind `AUTOPILOT_PUBLISH_TOKEN`. Deviations:
  - The stdio usage snippet is in the module docstring, not a README.
  - The server writes a call log that the harness ingests, instead of calling `trace.log_event` directly.
- [x] **D1-B harness core** (`harness/schemas.py`, `trace.py`, `guardrails.py`, `evals/test_harness.py`): all models plus `passes_threshold` and `apply_threshold`; trace with `start_run`, `log_event`, `step`, redaction, locking and atomic writes; all six guardrails. Additions beyond the PDF:
  - A `BrandBrief` model.
  - `Critique` requires one reason per score.
  - `Draft.text` is capped at 300 characters in the schema.
  - `harness/fileio.py` (lock and atomic-write helpers).
  - The rate cap uses a rolling 24-hour window.
- [x] **D1-C** `mcp_server/bluesky.py` (atproto 0.0.73) and `harness/llm.py` (fallback chain, backoff, budgets, repair, MockLLM) (`cd0e1f2`, `2b9d1d8`)
- [ ] R1 diff review (read-only reviewer session) run on the P1 diff

**Block 4: integrate and inner loop**
- [x] Merge A, B and C and run tests (single branch, so no merge was needed; 98 pass)
- [x] **D1-D** `agents/writer.py`, `agents/critic.py`, `loops/inner.py`, `scripts/run_post.py` (`--dry-run`, `--approve`), with tests (pass on attempt 1, pass on attempt 3, escalation after 3, no publish on a guardrail failure) (`7ee2e88`)

**Block 5: first live post**
- [x] Run with approval ON, read the draft and the critic's reasons, approve (`run_20261022_092913_bde119`)
- [x] Post is live, and `data/runs/run_20261022_092913_bde119.json` holds the full trace
- [x] Commit and push with secrets only in `.env` (secret scan clean on every commit)

### Day 2 (Fri Oct 23): full loops, evidence, deploy
Goal: the cron runs unattended, and the second run's plan reflects the first run's learning.

**Block 1: outer loop (D2-A)**
- [~] `get_metrics` against real Bluesky: harness-side `fetch_metrics`, `measure.py` and not-found strikes (issue 16) are built and tested with a fake client; not read live yet
- [~] `agents/analyst.py` ("not enough data" on zero or low engagement): done offline
- [~] `agents/planner.py` (reads learnings, cites one that has signal, harness checks and retries once): done offline
- [~] `loops/outer.py` (plan, inner loop, guardrails, publish, measure, learn; `--measure-only`; run summary; decision 4.3 applied): done offline
- [ ] 3-5 more real posts (2 done; with the 60-minute gap this takes about 3+ hours of wall time)

**Block 2: prove the critic (D2-B)**
- [ ] About 10 drafts, including bad ones, hand-scored; `evals/calibrate_critic.py`; `data/calibration/report.md`; one rubric fix with before and after numbers

**Block 3: failure-handling tests (D2-C, tests 1-7 verbatim)**
- [x] Revision cap, JSON repair, rate cap, banned phrase, 429 fallback, publish ordering, prompt injection (`evals/test_failure_handling.py`, each driven through a whole `run_post` and checked in the trace or call log)
- [ ] Force each failure once by hand against the real system and confirm it in the trace (the tests use mocks; this step is not done)

**Block 4: deploy (D2-D)**
- [~] `.github/workflows/run.yml` written (cron 06:17 UTC assumed, `workflow_dispatch` with `dry_run`, Python 3.11, concurrency group, 20-minute timeout, commits `data/`); the schedule is measure-only (decision 4.11). YAML parsed and the secrets check and clean-checkout boot tested locally; never run on GitHub
- [~] Separate CI workflow running pytest on every push: `ci.yml` written, not yet run
- [~] `docs/DEPLOY.md` written; still to do: merge to `master`, add the four repository secrets, a manual run, then a scheduled run
- [ ] Trace page deployed (Cloudflare Pages or Vercel)

**Block 5: Tier A runtime (P2, our addition)**
- [ ] P2: Hermes runtime behind the proxy, time-boxed to about 2 hours, *after the first live post* (decision 4.2). Design in section 9.

**End-of-day checks**
- [ ] The second run's plan cites a learning from the first
- [ ] A scheduled run completed unattended
- [ ] Tests pass locally and in GitHub Actions

### Day 3 (Sat Oct 24): polish, record, rehearse
- [ ] **D3-A** dashboard (overview, posts, learnings, trace view first) plus `scripts/export_dashboard_data.py`; check on phone and laptop
- [ ] **D3-B** `README.md` and `docs/DEMO.md` (with a planted bad brief that triggers a critic rejection and a guardrail block)
- [ ] Record the backup demo video; rehearse twice; Q&A prep
- [-] **D3-C** Scout (optional; first item on the PDF's cut list)

### Review prompts (before every merge)
- [ ] R1 diff review
- [ ] R2 explain-it on each module
- [ ] R3 adversarial tests
- [ ] R4 secret scan of the repo and its history (an ad-hoc scan of the P1 commit was clean)

## 7. Open issues from the Opus audit (2026-10-22)
| # | Issue | Status |
|---|---|---|
| 1 | The plan never reached a live post on Day 1 | **Resolved by decision 4.2** (live path first) |
| 2 | Tier A is much bigger than the PDF's 2-hour Hermes budget | **Mitigated**: P2 time-boxed to about 2h, with a direct-OpenRouter fallback |
| 3 | A 60-minute gap means at most 1 publish per run, but the outer loop writes every post | **Resolved by decision 4.3**; implement in `loops/outer.py` |
| 4 | The 40-attempt daily quota may not cover one run | **Superseded by issue 18** (limit looked up; one run costs 2-3 requests normally) |
| 5 | CI is Ubuntu, but the P2 design relies on Windows facts (`taskkill /T`, native install) | Open: make P2 cross-platform before D2-D |
| 6 | Fallback chain proven for only 1 model | **Resolved** (step 3: 3 models pass a real tool call) |
| 7 | Nothing committed | **Resolved** (`f774123`, `d10bb10`, pushed) |
| 8 | Handoff only in a temp folder | **Resolved** (this file, committed at the end of Day 1) |
| 9 | `CLAUDE.md` paste artifacts | **Resolved** (`d10bb10`) |
| 10 | Tests never run on 3.11 | **Resolved** (`.venv311`; 229 pass on 3.11 and 3.14) |
| 11 | The handoff said the main branch was `main` | **Resolved** (it's `master`) |
| 12 | Call log written after the tool returns, so a failure after a real post is mis-logged | **Resolved** (`cd0e1f2`: pending record before the Bluesky call; seen in the live post's call log) |
| 13 | `check_banned` matches whole words only ("cures" slips past "cure") | Reported; tracked as issue 17 |
| 14 | Test network guard doesn't block DNS lookups | Open, low |
| 15 | Narrow stale-lock race after a crash | Open, low |
| 16 | `get_post_metrics` raises `BlueskyNotFound` when called right after posting, because the AppView hasn't indexed the post yet (seen in the step 4 throwaway post). It should retry briefly or treat a very new post as "not yet indexed", never as deleted, and the analyst must not read it as a deleted post | Open, D2-A |
| 17 | `check_banned` misses word variants (cures, Glutenfree, Actnow, "best bakery in the town"); must be fixed before the Day 2 cron (D2-D). Suggested: prefix matching, no-space forms, and a variants list in the brief | **Fixed** by review item 27 (committed in `e48066d`) |
| 18 | OpenRouter free-tier limit: 50 requests/day assumed (under $10 of credits ever bought), 1,000/day with $10+; 20/min either way. One `run_post` costs 2-3 requests normally, up to 9 with 3 attempts, hard cap 36 | **Decided** (Oct 23): stay at $0 and ration; the limit is still unconfirmed for this account |
| 19 | URL in posts is plain text (no link facets); confirmed on the first live post | **Fixed** (`3935a10`), live-verified; local ISSUES_LOG 4.2 (not in git) still says Open |
| 20 | Critic passed a claim not in the brief ("starter smells like yogurt"); it is not given the planned post or a fact-check rule | **Fixed offline** (`3d96fe7`); real-model behavior unproven until D2-B; local ISSUES_LOG 7.4 (not in git) still says Open |
| 31 | `trace.py` keeps only the first 2,000 characters of each call summary (`SUMMARY_MAX_CHARS`), and the critic's messages run past 3,000, so the critic's trace events never show the draft or the planned post (confirmed in a dry run). Suggested fix: head-and-tail truncation in `harness/trace.py`, with its own tests | **Fixed** (`3f4d25a`): the trace keeps the first 500 and last 1,500 characters with a marker, after redaction; a critic trace test shows the draft and planned post survive. Old traces keep the old format |
| 32 | Writer and critic let a draft drift off the planned topic: the writer prompt never said the topic outranks the brief's class emphasis, and the critic never checked topic fit (`ee5488`: a free-sample-loaf topic became a bulk-fermentation draft scoring all 5s) | **Fixed offline** (`ffe39e1`: writer `TOPIC_RULE`, critic `TOPIC_FIT` caps clarity at 2); real-model behavior unproven |
| 33 | A retired model (minimax `:free`, 404 from Oct 22) cost one upstream attempt on every `chat()` call, two of the writer's eight in `c48e24` | **Fixed** (`fc3abf0`: a 404'd model is skipped for the rest of the run); still remove dead ids from `OPENROUTER_MODELS` |
| 34 | Free model pool is thin and unstable: poolside, gemma and xingchen 429 at times, cohere truncates, nemotron 404, poolside expires Oct 31 | Open: chain reordered Oct 23 (decision 4.9); flint added but proven for one tool call only; re-probe xingchen later |
| 35 | `run_post` enforces "approval off only for a dry run" in its CLI only (`run_outer` enforces it inside `run_outer()` too) | Open, low |

**Independent review of `feat/hermes-runtime` (Oct 22, end of Day 1).** Each item was reproduced with a failing offline test before it was fixed. Items 21-24 were also mutation-checked (each fix reverted makes a test fail). Committed in `e48066d`.

| # | Review finding | Status |
|---|---|---|
| 21 (R1) | After Bluesky accepts a post, a failed call-log or `approved.jsonl` write raised, so the run reported "failed" and the row was lost; the next run could post again | **Fixed**: `publish()` writes a `pending` row before the post and a `published` row after; post-success write failures become warnings; `server._logged` no longer raises on a lost log line; an unsettled pending row counts toward the rate cap and duplicate check; an unknown outcome exits 4 and keeps counting |
| 22 (R2) | `live_records()` skipped unreadable lines in `approved.jsonl`, so the rate cap could undercount | **Fixed**: any unreadable line raises `ApprovedLogError`; the run is blocked (exit 5) |
| 23 (R3) | `publish()` trusted a caller-supplied gate dict | **Fixed**: `publish()` re-runs length, banned, rate cap and duplicate on the exact text it sends, and takes only the human's approval from the caller |
| 24 (R4) | Two overlapping runs could both pass the rate cap; `now` was taken before the approval wait | **Fixed**: one lock (`data/publish.lock`) around re-check, pending row, post and result row; publish reads a fresh clock |
| 25 (R5) | A model error on attempt 2 or 3 returned "failed" and dropped the drafts | **Fixed**: escalates to human review with the drafts and the error (rule 6); "failed" only when no draft exists |
| 26 (R6) | Unexpected tool exceptions crashed the agent; a TypeError inside a tool looked like bad arguments | **Fixed**: arguments are bound first ("invalid arguments"); other exceptions become a "tool failed: <type>" result |
| 27 (R7) | `check_banned` missed inflections, spaced and dotted letters, no-space forms (issue 17) | **Fixed**: inflection forms per word, joined single letters, articles ignored, no-space and split forms, and `banned_variants` in the brief (`results guaranteed`, `do not miss out`, `curative`). No false positives on the real posts or the brief. Issue 17 closed |
| 28 (R8) | A missing or invalid brief crashed after the trace was created; the post day was the local date | **Fixed**: the brief and the LLM config are checked before the trace exists (exit 2, no trace); the day is the UTC date |
| 29 (R9) | The writer's revision prompt said "4 or more" whatever `--min-score` was | **Fixed**: uses the actual `min_score` |
| 30 (R10) | Stale-lock race (issue 15) | **Left as is**: the publish lock does not cover it. It holds for seconds, far below the 60-second stale threshold, so a live lock is not broken in practice |

## 8. Environment facts
- **Python:** system and `.venv` are both 3.14.8. `.venv311` is 3.11.16 (installed with the user's `~/.local/bin/uv`, not Hermes's). Both have `requirements.txt` installed: `mcp==2.0.0`, `pydantic 2.14.1`, `atproto==0.0.73`, `pytest 9.1.1`. Run tests in both: `.venv/Scripts/python.exe -m pytest -q` and `.venv311/Scripts/python.exe -m pytest -q`.
- **Running a post:** `python -m scripts.run_post --topic "..." [--goal click] [--dry-run]`. Approval is on by default. For a rehearsal, set `AUTOPILOT_DATA_DIR` to a scratch folder (with a copy of `brand_brief.json`) so nothing lands in `data/`.
- **MCP SDK 2.0 API:** `from mcp.server import MCPServer`, `@server.tool()` or `server.add_tool(fn)`, and `server.run("stdio")`. (It is not `FastMCP`.) Run the server as `python -m mcp_server.server` from the repo root.
- **Hermes:** native install v0.21.4 at `%LOCALAPPDATA%\hermes`, with its own Python 3.11.16 venv.
  - The user's global Hermes config uses a non-free provider. **Never touch it**; always run with an isolated, temporary `HERMES_HOME`.
  - Check the pinned commit with `git -C <install>/hermes-agent rev-parse HEAD`, **not** `hermes --version` (that triggers a network update check).
- **`.env`:** `OPENROUTER_API_KEY`, `OPENROUTER_MODELS`, `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD` all have values. **Never print or log them**; report presence only.
- **Recovering an unfinished "pending" row** (a crash or an unknown outcome during publish). An unsettled pending row counts as a post, so it blocks publishing for 60 minutes (gap) and counts toward the 24-hour cap until it is settled. Run these in Git Bash from the repo root, with no `run_post` running. The commands were tested offline on a scratch data folder.
  1. List the unsettled rows:
     `.venv/Scripts/python.exe -c "from harness.publish import live_records; [print(r['post_id'], r['posted_at'], r['text']) for r in live_records() if r.get('status') == 'pending']"`
     The matching `run_id` is on the same `pending` line in `data/approved.jsonl`.
  2. Check whether the post is live, against the account's PDS (the source of truth; the AppView can lag, issue 16). Either open the profile in the Bluesky app, or read the latest records (read-only, no login):
     `curl -s "https://bsky.social/xrpc/com.atproto.repo.listRecords?repo=<DID>&collection=app.bsky.feed.post&limit=10"`
     Look for the same text; note its `uri` and `value.createdAt`.
  3. Settle the row. Append one line through the locked writer; never edit or delete earlier lines.
     - **Not on the account:**
       `.venv/Scripts/python.exe -c "import sys; from harness.fileio import append_jsonl; from harness.publish import approved_path; run_id, post_id = sys.argv[1:3]; append_jsonl(approved_path(), {'status': 'failed', 'run_id': run_id, 'post_id': post_id, 'reason': 'settled by hand: not on the account'})" <run_id> <post_id>`
     - **Live:** record it with its real time, so the rate cap measures from the actual post:
       `.venv/Scripts/python.exe -c "import sys; from harness.fileio import append_jsonl; from harness.publish import approved_path; run_id, post_id, uri, created_at, text = sys.argv[1:6]; append_jsonl(approved_path(), {'status': 'published', 'run_id': run_id, 'post_id': post_id, 'text': text, 'uri': uri, 'posted_at': created_at, 'dry_run': False, 'reason': 'settled by hand: found on the account'})" <run_id> <post_id> <uri> <createdAt> "<text>"`
  4. Run step 1 again; the row should be gone. If unsure whether it is live, leave it pending: it only delays the next post.
- **Data paths:** `AUTOPILOT_DATA_DIR` overrides `data/`. The MCP call log goes to `AUTOPILOT_TOOL_LOG`, defaulting to `data/runtime/mcp_calls.jsonl` (git-ignored).

## 9. P2 reference: verified Hermes behavior and the Tier A design
Kept from the original handoff. Build this only after the first live post, within about 2 hours.

**Verified Hermes behavior (evidence in `.hermes_spike/verify/out/`).** The Opus audit re-checked the `-z` claim (confirmed in `hermes_cli/oneshot.py` around line 574) and the pinned commit. The rest comes from the previous session's experiments.
- **Invocation:** `hermes chat -q <task> --oneshot -Q --format stream-json -t autopilot`. Never `-z`: it builds `AIAgent` without `max_iterations`, so `agent.max_turns` is ignored (one test made 610 tool calls in 2 minutes).
- **Always pass `-t <mcp server name>`.** Without it Hermes offers 24 built-in tools.
- **MCP tool names:** `mcp__<server>__<tool>` (double underscores). A server with zero tools gives the role `[]`, which is how the critic gets none.
- **Required config keys:**
  - `tools.tool_search.enabled: off`
  - `auxiliary.title_generation.enabled: false`
  - `memory.memory_enabled: false` and `memory.user_profile_enabled: false`
  - `model: {provider: custom, base_url, api_key, streaming: false}`
  - `agent.api_max_retries: 1` and `agent.auto_recovery_cycles: 0`
  - `plugins.enabled: [autopilot_trace]` and `plugins.hook_callback_timeout`
  - **`updates.check: false`** (otherwise chat mode calls the GitHub API)
- **Role prompt:** goes in `HERMES_HOME/SOUL.md`. `agent.system_prompt` is ignored in one-shot mode. About 9K characters of Hermes boilerplate stay on every call.
- **Plugin hooks:**
  - Hooks available: `pre_api_request`, `post_api_request`, `api_request_error`, `pre_tool_call`, `post_tool_call`.
  - `pre_tool_call` fails closed: a veto blocks the call, and if the hook raises or times out the tool still doesn't run.
  - Tool calls outside the offered set are rejected by Hermes, which aborts after 3 strikes. These produce no tool hook events.
  - When the iteration limit is hit, Hermes makes 2 summary LLM calls that **bypass the hooks**. Only a proxy sees them, which is why the design has one.
- **Usage data:** `--usage-file` works only with `-z`. In chat mode, the stream-json `result` line carries the session ID, exit code, final text and token totals.
- **Proxy refusals:** a non-retryable 400/403 stops Hermes immediately (the proxy uses 403 for an exhausted budget).
- **Windows cleanup:** `taskkill /T /F` cleans up the whole process tree. **Linux needs an equivalent** (process group kill) for CI.
- **Key safety:** Hermes backs up `config.yaml` into `home/backups/`, so never put a real key in the Hermes config. The key stays in the proxy only.

**Tier A design (approved; implement in P2)**
- **Flow:**
  1. `agents/<role>.py` is called by the orchestrator.
  2. `harness/runtime.py` validates the output, with 1 repair.
  3. `harness/hermes_runner.py` sets up a temp `HERMES_HOME`, starts the proxy, runs Hermes, kills the tree on timeout, ingests the records and runs the cross-check.
  4. `harness/llm_proxy.py` is the only holder of the key and uses the `llm.py` chain.
  5. The MCP server is started with `AUTOPILOT_ROLE=<role>`.
  6. Python gates (`passes_threshold`, `guardrails.run_all`, `require_approval`) run, then `harness/publish.py`, the only caller of `publish_post` and `save_learning`.
- **Role allowlists** (`ROLE_TOOLS` in `mcp_server/server.py`, already implemented):

  | Role | Tools |
  |---|---|
  | planner | `get_brand_brief`, `get_learnings` |
  | writer | `get_brand_brief` |
  | critic | none |
  | analyst | `get_metrics` |
  | harness | all 5 (`publish_post` and `save_learning` are harness-only) |

- **Fields the harness overwrites:** `Critique.passed`, `Draft.post_id`, `Draft.attempt`, `Learning.run_id`, `Learning.post_id`, `Learning.metrics`.
- **Proxy:**
  - Routes to `:free` models only, after the metadata check.
  - Retry policy as in D1-C; 401/402/403 never fall back.
  - Per-invocation budgets: Hermes requests 8/5/2/8, upstream attempts 12/8/4/12, timeouts 180/120/90s.
  - Daily cap on upstream attempts in `data/runtime/quota.json` under a lock, failing closed. **The cap of 40 must be re-checked against the real free-tier limit** (issue 4).
  - Rejects `stream: true`; redacts secrets; records every request.
- **Cross-check (`harness/trace_check.py`)** fails closed on:
  - `exit_failed`, `stream_incomplete`, `plugin_missing`, `session_mismatch`
  - `llm_unmatched`, `llm_extra_unexplained` (except 1-2 after an iteration limit)
  - `tool_unauthorized`, `tool_mismatch`, `usage_mismatch`, `final_text_mismatch`
  - budget or quota errors, `secret_detected`, `trace_write_failed`

  A failed invocation is retried at most once, then the post is escalated or blocked.
- **Trace and run summary:**
  - Each upstream attempt is an `llm_call`; fallbacks and backoffs are `decision` events.
  - The final `decision` event has `summary_in="run_summary sha256=<hex>"` and the full JSON summary (`schema_version, run_id, plan, outcomes, learnings`). It is written with `truncate=False` (already supported) but is still redacted.
- **Offline tests:**
  - Fixture metadata in `tests/fixtures/openrouter_models.json`.
  - Non-loopback sockets are blocked (`conftest.py`, already implemented).
  - Subprocesses go through a loopback egress sentinel and must make zero external requests; no `.update_check` file may appear.
- **Phases:** P2 runtime, P3 agents and loops, P4 dashboard export, P5 live smoke test. **This order is superseded by decision 4.2**: the live path (task steps 3-5) comes first, and P3's writer, critic and inner loop were built for step 5 as D1-D, calling `llm.py` directly.
- **Rollback:**
  - Revert per phase with git.
  - Purge a run's data by `run_id`.
  - Delete `data/runtime/`.
  - Switch a role to a direct `llm.chat` runtime (needs approval).

## 10. Working style the user expects
- State a plan before large changes and **wait for approval**. After each step in a task list, **stop and report**.
- **Ask before any external call** (OpenRouter, Bluesky, GitHub) and before commits or pushes. Approval for one step does not carry over to the next.
- Report exact commands, evidence, the files touched and honest limitations, including your own mistakes.
- Do not redo or re-ask settled decisions (section 4). Do not invent MCP tools or rename the PDF's files without a reason.
- Follow CLAUDE.md's definition of done: tests pass, no secrets in the diff, trace verified by running once, and a 3-line summary.
- **Never add attribution trailers to commits or PRs.**
- **Next action (Oct 23):**
  1. Wait for the free models' 429s to clear, then make **one** live post in a real terminal with a specific topic (the free-sample-loaf topic is a known drift case and tests the new writer and critic rules). The user must be present: approval stays on. Check the trace for which model wrote and scored it.
  2. Issue 31 (trace truncation) is fixed; the next live run is the first whose critic trace shows the draft and the scores.
  3. First real `run_outer` (try `--measure-only` first, since it is cheapest), then D2-B calibration. D2-C is done; D2-D is written.
  4. Merge `feat/hermes-runtime` to `master` (a PR), add the four repository secrets and do the first manual run, following `docs/DEPLOY.md`. Until the workflows are on `master`, neither the schedule nor "Run workflow" works. Pushing and merging are the user's call.
  5. Item (d) stays decided: stay at $0 and ration requests (about 42 of 50 used by 09:05 UTC on Oct 23, counting 4 probe requests the repo's own count misses).
  6. Day 3 (Oct 24) is mostly offline: D3-A dashboard and `scripts/export_dashboard_data.py`, D3-B README and `docs/DEMO.md`, the backup video.
- **Local ISSUES_LOG (not in git) is behind:** it still says issues 19 and 20 are Open and has no entry for issues 32-35.
- **Process note:** a status question is not a go-ahead. Do not start editing code until the user says so.
