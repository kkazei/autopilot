# Autopilot handoff, updated 2026-10-25 (final day; evidence stages A to F done or closed, see the Oct 25 update)

Status key: `[x]` done, `[~]` partly done, `[ ]` not started, `[-]` deferred by decision.

## 1. Sources of truth
- **Repo:** `C:\Users\jirro\orca\projects\autopilot` (Windows 11, PowerShell plus Git Bash).
  - Remote: `https://github.com/kkazei/autopilot` (private).
  - Main branch `master`. Work now goes through short branches and pull requests: PRs #1 to #11 are **merged** (see the Oct 24 update in section 2 for #5 to #11; #13 is merged too, per the user; the list that follows is the Oct 23 state) (#1 all of Day 1-2 code, #2 first learnings, #3 the critic calibration tool, #4 the hand scores, the first partial calibration run and the handoff); **PR #5** (GitHub Actions bumped to v7 for Node 24, plus one bot data commit from its test run) is open. The user merges PRs; Claude does not (the permission checker blocked a merge by Claude).
  - **The GitHub workflow pushes data commits straight to `master`** (author `autopilot[bot]`, message `data: scheduled run <id>`). Run `git pull` before posting or branching, so you have its traces and any learnings it saved.
- **Build plan (authoritative):** `C:\Users\jirro\Downloads\Autopilot 3-Day Build Plan and Claude Code Prompts.pdf` (30 pages).
  - It holds the repo layout, the data contracts, prompts D1-S to D3-C, the critic rubric, the failure table, deployment and the demo script.
  - The Read tool can't render it on this machine; use `pdftotext -layout` (available in Git Bash).
- **`CLAUDE.md`:** the project rules. Paste artifacts were removed in `d10bb10`, and it now also says no attribution trailers.
- **`docs/ISSUES_LOG.md`, local only, not in git:** what went wrong and how it was resolved (for the interview). It is excluded through `.git/info/exclude`, so it stays on the user's disk only. Keep it current. References below say "local ISSUES_LOG".

## 2. Where we are (one-screen summary)

### Final state (Oct 25, about 12:05 UTC; read this first)
**Done.** Every evidence stage is closed (table below). Live posts end at 3 (one new today). The dashboard is live and rebuilds itself on every push to `master`, including the scheduled bot's pushes (seen at 11:27 UTC).

**Git.** `master` has PRs #15 to #18 merged: #15 the planner-angle prompt fix, #16 the morning data and stage D evidence, #17 the writer's repair target of 240, and #18 the dashboard visual refresh (ui-ux-pro-max skill, CSS and two HTML lines). **PR #19** holds the afternoon data and the stage F evidence. **The docs PR** (`docs/final-oct25`) holds this file, README, `docs/DEPLOY.md`, the dashboard's partial list (`scripts/export_dashboard_data.py` and its test) and the removal of `docs/DEMO.md` from the repo. The user merges both.

**Model chain (changed by the user, seen at 11:49 UTC):** `OPENROUTER_MODELS` in `.env` is now poolside, flint, **nvidia/nemotron-3-ultra-550b-a55b:free**, gemma; cohere is gone. This supersedes decision 4.9's list. nemotron-3-ultra produced today's stage F plan. The GitHub secret `OPENROUTER_MODELS` may still hold the old chain; the scheduled run only measures, so it matters only when the analyst is called.

**Quota at 12:01 UTC:** 27 in the repo count plus 15 requests from scratch folders (stage D 7, stage F 8) that `quota.run_cap` does not see, so about 42 of 50 used. No more model calls are planned today.

**Left after today:** the user records the backup video and rehearses (`docs/DEMO.md` and `docs/QA_PREP.md`, both local only). Next steps, in the README: a draft queue with a one-click approval page; a code check for times, prices and numbers not in the brief; re-measuring "not enough data" posts; an automatic check of the account's server after a publish timeout (issue 44); replacing poolside's `laguna` id before Oct 31.

### Oct 25 update (read this first; it supersedes the Oct 24 and Oct 23 statements below wherever they differ)
**Repo.** PRs #15 (issue 39 prompt fix), #16 (data: third live post, a declined run, stage D evidence), #17 (writer repair target 240), #18 (dashboard visual refresh), #19 (afternoon data, stage F evidence) and the final docs PR carry today's work. Tests: 541 on Python 3.11 and 3.14 after the docs PR (540 on `master`, plus one export test).

| Stage | Oct 25 result |
|---|---|
| A critic clarity fix | Done Oct 24 (agreement 6 to 7 of 10, within noise). **Issue 40 closed as a documented limitation; no more tuning** (decision 4.17). |
| B real-model `run_outer` dry run | Done Oct 24. Issue 39 (planner angles) fixed in prompts (#15), offline only. |
| C live posts with approval on | **Closed: 1 new live post** (`run_20261025_092654_7bb28e`, 09:27 UTC; 4 likes from the user's friends when measured), 3 live in total; post #5 dropped for quota. Declined at approval: `092527_f232f7` (invented "10am-1pm") and `102826_666dc2` (invented crust sounds and looks, "shaped by steam"; scored 5/5 even after #15). `103042_bfa092`: approved, then the Bluesky call timed out; the pending row blocked any retry, the account's server (listRecords) showed no post, and the row was settled `failed` by hand (review item R1 working for real). `103506_4ca574` and `103526_395daf`: the writer drafted about 500 characters and the one repair stayed over 300 (391, 303), so both stopped cleanly; fixed by #17 (repair aims at 240, unproven live). `115535_68f04e` (the last attempt, after #17): 300 characters, so the length held, but "A few spots remain for this weekend" is invented scarcity; the critic named it yet scored policy_risk 4, so it passed the threshold; declined at approval. |
| D force the D2-C cases | **Closed** (`data/evidence/stage_d/README.md`). Case 3 rate cap **passed** (0 requests). Cases 2, 5, 6 proven by existing real traces. Case 7 injection **partial**: the writer resisted it, then the run stopped at a length repair before the critic. Case 4 **not forced**: the writer avoided the banned phrases but used urgency; the critic gave 5/5; approval caught it. Case 1 **skipped** by decision. |
| E scheduled run | **Confirmed**: run 40088006393 was `event: schedule`, Oct 24 10:58 UTC (cron 06:17, about 4h40m late), success, measure-only, 0 requests. Run 40084089747 (09:59) was a manual dispatch. **Oct 25: fired again** (run 40188905174, `event: schedule`, 11:26:57 UTC, about 5h10m late, success, 0 requests). It skipped `post_fa922d48`, 41 seconds short of 2 hours old, as designed. Its data push rebuilt the dashboard with nobody involved. |
| F plan cites a learning | **Passed, planner only** (`data/evidence/stage_f/README.md`). Live measure `run_20261025_112952_3635b0`: `post_fa922d48`, 4 likes **from the user's friends**, so the analyst saved the first learning with signal (2 requests). Then the real planner with the real learnings and the harness plan check, in a scratch folder: the first try (`114552_876bb2`, budget 4) failed cleanly on a 429, a 120 s timeout, a local DNS failure and a flint truncation; the retry (`115028_61726b`, budget 5) passed via nemotron-3-ultra: `check plan (attempt 1)` ok, citing `[learning:post_fa922d48]`. The use is shallow (one post's framing), and some topics go beyond the brief. Planner only, to keep quota for a live post; the full `run_outer` path ran in stage B. |

**Finding (issue 42).** On real drafts the critic scored 5/5 an invented class time ("10am-1pm", `run_20261025_092527_f232f7`, declined), invented crust sounds and looks (`102826_666dc2`, declined, after the #15 fact-check change), a claim about customers and urgency pressure (stage D case 4); and it named invented scarcity ("a few spots remain", `115535_68f04e`) but scored it 4, against its own rule of 2 or lower for urgency pressure. The writer and harness behaved; the critic's fact and policy checks are not reliable on the free model. Human approval caught every case. Stated in README, DEMO and the dashboard.

**Local-only docs (Oct 25, the user's choice):** `docs/DEMO.md` (the demo and video script) is no longer tracked; it was removed from the repo in the final docs PR and kept on the user's disk, like `docs/ISSUES_LOG.md`. Older versions remain in git history (PRs #7, #9). `docs/QA_PREP.md` (Q&A notes) was never committed. Both are in `.git/info/exclude`.

**Dashboard deployed:** https://autopilot.jirroaeron.workers.dev/ (Cloudflare Workers Builds connected to the repo; it rebuilds on every push to `master`, first production build after the PR #17 merge, verified at 11:00 UTC: 3 live posts, 19 runs, today's traces). Settings in `docs/DEPLOY.md`. The first manual upload at `restless-morning-449e.jirroaeron.workers.dev` does not update; the user can delete it.

**Quota note.** Requests made from a scratch data folder are not counted by `quota.run_cap` (issue 41): stage D cases 4 and 7 made 7 such requests on Oct 25, and stage F made 8.

**Left after today:** replace poolside's `laguna` id before Oct 31 (decision 4.9); the backup demo video and rehearsal are the user's; R1-R3 review prompts, Hermes for the other roles and issue 5 were cut.

### Oct 24 update (read this first; it supersedes the Oct 23 statements below wherever they differ)
**Where the repo is.** `master` is at `0033d85` or later. PRs #1 to #11 and **#13 (data: the real-model outer-loop dry run) are merged** (the user merged #13 after this session opened it; its merge commit was not seen here), and this handoff goes in its own docs PR. Tests: **536 passing** on Python 3.11 and 3.14 (535 plus one new rubric test); CI was green on #10 and #11 (never checked on #13 or the docs PR).
- #5 Actions to v7; #6 the opt-in Hermes writer runtime (`AUTOPILOT_WRITER_RUNTIME=hermes`; `.env` says `direct`, so it is off); #7 static dashboard, `scripts/export_dashboard_data.py`, README, `docs/DEMO.md` and a planted bad brief (`docs/demo/bad_brief.json`, `scripts/demo_bad_brief.py`); #8 the complete calibration baseline and the Hermes smoke-run trace; #9 README, demo and export text stating the complete result; #10 the critic clarity change; #11 its before/after data.
- Hermes smoke run: `run_20261024_092855_f3905e`, a dry-run `run_post` with the writer through Hermes, 6 model requests in its trace, Hermes cross-check passed. One run only; Hermes is still opt-in and not used by default.
- Offline forcing of the 7 D2-C cases with scripted models was done by hand earlier (commit `21008a3`); forcing them against a real model has not been done.

**Evidence stages from the Oct 24 brief** (order A, B, F, D, C, E; stop between stages; the user's go before every OpenRouter, Bluesky or GitHub call):

| Stage | State |
|---|---|
| A critic clarity fix, measured | **Done** (#10, #11). Result below. |
| B planner and write-and-critique half on a real model | **Done as a dry run** (trace merged in #13). Result and problems below. |
| F "plan cites a learning" | Not started. Both real learnings are "Not enough data yet", so it needs an openly labelled planted example, or a real post with engagement. Never present planted data as real. |
| D force the 7 D2-C cases once | Not started. Next step is an offline plan: which cases can be forced against the real harness with no quota, and which need a real model. |
| C 3-5 more live posts, approval on | Not started. The user runs them in a real terminal. |
| E scheduled run confirmation | Not started (see below). |

**A. Critic calibration, complete runs (poolside scored all 10 drafts both times).**
- Baseline `run_20261024_092334_1f3174`: agreement 6 of 10; too lenient on d03, d06, d08, d10; too strict on none. Mean absolute error / bias: voice 1.00/+0.20, clarity 1.30/+0.70, cta 0.70/+0.10, policy_risk 0.40/+0.20. `data/calibration/report.md`.
- After one change to the clarity line of `RUBRIC` in `agents/critic.py` (a 3 anchor for a main idea plus a competing second message; the closing call to action alone is not a second idea): `run_20261024_101844_e0d3ed`, `data/calibration/report.after-clarity-anchor.md`. Agreement 7 of 10; too lenient on d03, d06, d10; voice 1.20/+0.20, clarity 1.10/+0.30, cta 0.80/+0.00, policy_risk 0.40/+0.20.
- The criterion was fixed before the run (clarity error below 1.30, agreement at least 7, d01 and d04 still pass, all 10 scored by poolside) and **was met narrowly**. State it exactly this way: the gain is one draft (d08) and within run-to-run noise; it was tuned and measured on the same 10 drafts; d03, d06 and d10 are still lenient; voice and CTA error rose slightly. **Do not say the clarity problem is fixed.** No further tuning was done. The hand-score review used the same rubric (circular); 34 of 40 hand scores are the user's, 6 adjusted at their request.

**B. Real-model dry run of `run_outer`** (`run_20261024_114318_baec64`, 13 requests of its 16 cap, exit 0). Command: `python -m scripts.run_outer --dry-run --no-approve` on a scratch copy of `data/` (see section 8). The planner (cohere answered after poolside 429 x3, flint truncated at 4,096 tokens, gemma 429 x3) produced 5 posts that passed the harness check; today's post was selected; the writer's first draft was 368 characters and the repair step fixed it; the critic (poolside) gave 5/5/5/5 and the harness set `passed`; all 5 guardrails and the 4 publish re-checks passed; it published only to `dryrun://post_159be0c4/...`. Limits: approval was off, no Bluesky calls, the plan was not saved, one run. **Problems found, none fixed yet (the user has not decided):**
1. The planner's `angle` fields are invented sensory claims ("crust that cracks like leather"). They become the planned post, which the critic's fact check treats as supported, so an unsupported claim can pass through the plan.
2. The critic gave clarity 5 to a draft with a scene, a "mistakes happen" aside and an invitation: the d03/d06 pattern.
3. The free chain is unstable: the planner alone cost 8 upstream attempts.

**E. Scheduled run: unconfirmed.** At 08:33 UTC on Oct 24 no `schedule` run had fired. A commit `data: scheduled run 40084089747` by `autopilot[bot]` then landed on `master` at 09:59 UTC. The commit message is the same for a manual dispatch, so whether it was a `schedule` event is **not confirmed**: read the Actions log (`gh run view 40084089747 --json event,createdAt,status,conclusion`; needs the user's go). Then check the next 06:17 UTC run on Oct 25.

**Live posts and learnings.** Still 2 live posts, both with zero engagement; `data/learnings.jsonl` holds the 2 "Not enough data yet" learnings. No new live post was made on Oct 24.

**Quota (50 requests/day is assumed, unconfirmed).** Repo count at 11:50 UTC on Oct 24: **45 of 50 used, 5 left** (13 at 09:23, 6 at 09:29, 13 at 10:18, 13 at 11:43; the Oct 23 requests have aged out). They age out at the same clock times on Oct 25, so 18 are free after 09:23 UTC, 24 after 09:29, 37 after 10:18 and all 50 after 11:43. Always recount (`.venv311/Scripts/python.exe -m evals.calibrate_critic --check` prints it, no model calls). Note: a trace must be in `data/runs` to be counted, so `git pull` first: #13 brought in the stage B trace, which makes the repo count 45 (it read 32 before).

**Next actions (Oct 25), in order, each needing the user's go before any external call:**
1. After 06:17 UTC: confirm the scheduled run from the Actions log (stage E; read-only `gh run list --workflow run.yml --limit 5 --json event,createdAt,conclusion`).
2. `git checkout master && git pull` (after the docs PR is merged), then recount the quota and show it before planning any live step.
3. Stage D plan (offline first, 0 requests): which of the 7 cases can be forced against the real harness without a model.
4. Decide with the user what to do about the three problems from stage B. The planner-angle one is a new item that was not in the brief.
5. Stage F: needs its own plan; likely real-model requests, so after 09:23 UTC.
6. Stage C: the user runs `run_post` in a real terminal, never with the `!` prefix, with a real topic, for example `.venv311/Scripts/python.exe -m scripts.run_post --topic "Free sample loaf with every first class booking" --goal click`. Each post costs 2 to 9 requests.
7. After the last stage: update this handoff, the README and the dashboard export text for the new results, in a PR, and give the user a one-screen list of proven, partial and unproven.

**Local repo cautions.** The local branch `docs/calibration-complete-text` carries an unpushed commit `5ea175e` that adds `data/runs/run_20261022_080056_bb7b95.json`. **Never push that branch or commit that file.** A copy of the file is in the Oct 24 session scratchpad; `git checkout master` from that branch deletes it from disk, so copy it first and put it back untracked. A `pr9-fix` worktree also exists in a session scratchpad. Local branches `data/calibration-complete`, `feat/dashboard-and-demo`, `feat/hermes-writer` are merged and can be deleted.
- **Status: Day 1 complete; Day 2 is code-complete and partly proven live, with evidence still outstanding.**
  - **Proven for real:** 2 live posts; the measure-only outer loop against the live account (2 learnings saved, no model call); the GitHub deploy workflow (one manual run succeeded); CI on every PR; and (Oct 24) a complete critic calibration before and after one rubric change, plus a real-model dry run of the planner and the write-and-critique half of `run_outer`.
  - **Not yet proven live (Oct 24):** more live posts, the scheduled run (unconfirmed, see the Oct 24 update), the by-hand failure forcing against a real model, and the "plan cites a learning" check. The planner and writer/critic inside `run_outer` have run once on real models, as a dry run with approval off.
- **Day:** Day 2 is Fri Oct 23 (now about 11:45 UTC). The schedule runs Oct 22-24.
- **Live posts so far (2):**
  - `run_20261022_092913_bde119` (Oct 22, 09:29 UTC), `at://did:plc:ogjf457tkxqfttvdsfbvjl7p/app.bsky.feed.post/3myhe2q5j432a`.
  - `run_20261023_071243_174bcb` (Oct 23, 07:13 UTC), a second Saturday-sourdough post.
  - Both were human-approved. Records are in `data/approved.jsonl`.
- **Three runs on Oct 23 ended without a post** (traces committed as evidence): `d77bec` (placeholder topic; the writer's draft was 312 characters and the repair failed), `ee5488` (the approval prompt had no stdin because the run used the `!` prefix; the draft had also drifted off the topic), `c48e24` (8-attempt writer budget used up; minimax `:free` retired, poolside and gemma 429, cohere truncated).
- **Built:** P1 harness core, `harness/llm.py`, the live Bluesky client, log-before-publish, writer, critic, inner loop, `harness/publish.py`, `scripts/run_post.py`, and (Day 2) link facets, the critic fact-check, topic-fit rules, dead-model skip, and the whole outer loop: `harness/measure.py`, `agents/analyst.py`, `agents/planner.py`, `harness/plan_state.py`, `harness/quota.py`, `loops/outer.py`, `scripts/run_outer.py`.
- **Tests:** 536 passing on Oct 24 (414 on Oct 23, as described here) on Python 3.14.8 (`.venv`) and 3.11.16 (`.venv311`), and on GitHub's Ubuntu runner with 3.11 (253 at the start of today).
- **Latest live attempt (Oct 23, 09:00 UTC, `run_20261023_090036_b0e71e`):** the topic fix worked (the draft was about the free sample loaf, passed on attempt 1, and the human declined it at the approval prompt, so nothing was published). Poolside 429'd then truncated; flint wrote the draft using 3,513 of its 4,096 tokens; poolside scored it 5/5. The draft was weak: it opened with the topic text word for word and said "Beginners often notice the crust and crumb first", an unsupported customer claim the critic missed. Both were addressed offline in `ca7af10` and are unproven on a real model. The repo's quota count undercounts by the 4 probe requests that went to a scratch folder: about 42 of 50 used by 09:05 UTC.
- **Day 2 progress:** (a) link facets (`3935a10`); (b) critic fact-check (`3d96fe7`); (c) banned variants and (d) quota decision done earlier; topic drift fixed offline (`ffe39e1`); dead-model skip (`fc3abf0`); (f) outer loop (four chunks, `c26f11f` to `fa24b3e`); D2-C failure tests (`d447a21`); D2-D workflows and `docs/DEPLOY.md` (`f9dff75`); all merged to `master` through PR #1. Then: first learnings (PR #2); the calibration tool with its hardening (PR #3, `abb99c8`, `3368c0d`, `8723983`); hand scores and the partial calibration run (PR #4, `6123c79`).
- **First real outer-loop run (Oct 23, `run_20261023_103918_bfa247`, `--measure-only`):** read both live posts from Bluesky, 0 likes, 0 reposts and 0 replies each, so both learnings are the fixed "Not enough data yet" sentence and no model was called. Issue 16 (fresh posts) did not arise; both posts were over 2 hours old.
- **First GitHub workflow run (Oct 23, manual, `dry_run=false`, run 39942468962):** green in 15 seconds. The secrets check, install, `--measure-only` and the data push all passed; it found nothing new to measure (learnings already on `master`) and pushed only its own trace (`0963ce2`). The log shows the four secrets as `***`; a search of the log for the real values found none. The first **scheduled** run is 06:17 UTC on Oct 24.
- **Calibration, first real run (`run_20261023_114019_557734`, partial; superseded by the complete runs in the Oct 24 update):** 7 of 10 drafts scored, all by `poolside/laguna-s-2.1:free`, 11 requests, saved as `data/calibration/report.partial-run_20261023_114019_557734.md`. Pass/fail agreement 5 of 7. The critic is **too lenient on d03 and d06** (all 5s; the user scored 5/3/4/4 and 4/3/4/5) and its largest gap is on **clarity** (mean absolute error 1.29, critic higher by 0.43). On the deliberately bad drafts (d02, d05, d07) it agreed that they fail. It stopped at d08: poolside 429 three times, then flint truncated at 4,096 tokens, using up the draft's 4-request budget; d09 and d10 were not attempted. A complete run and the rubric fix (with before and after numbers) are still to do.
- **Hand scores:** `data/calibration/drafts.csv` holds them, **34 of 40 numbers as the user entered and 6 adjusted by Claude at the user's request** ("decide for me"), only where a number contradicted the rubric's own wording (rule, list and reasons in `data/calibration/adjustments.md`; the user's first pass is `drafts.first_pass.csv`). No adjustment changes pass or fail (d01 and d04 pass before and after). The generated report discloses this and says the comparison is partly circular, because the review used the critic's own rubric. Say "34 of 40 are the user's own", not "all hand-scored".
- **Offline leftovers (Oct 23, all done):** a full dry run with a scripted model (the plan cited a synthetic learning, one post passed on attempt 1, all five guardrails and the four publish re-checks passed, it published to a `dryrun://` URI, 3 of 16 requests used, the run summary was complete; the learning was synthetic and is not evidence); the full-history secret scan (clean, see R4 below); the Actions bump (PR #5, the data-push step tested green on its branch); local branches tidied; and the local ISSUES_LOG updated.
- **Model chain (`.env`, changed today):** `poolside/laguna-s-2.1:free, recursive/flint-v1.0:free, google/gemma-4-31b-it:free, cohere/north-mini-code:free`. See decision 4.9 for why. In the calibration run poolside answered 7 critic calls in a row without trouble; it 429s in bursts. Flint spends close to its 4,096-token limit on one call.
- **Quota (Oct 23 figures; the Oct 24 count is in the Oct 24 update):** the repo's own count was 43 of 50 requests in the last 24 hours at 11:44 UTC on Oct 23, but it undercounts by the 4 probe requests that went to a scratch folder, so the real figure is about 47. Nothing more should be spent today. The oldest of today's requests (from about 07:12 UTC) age out of the 24-hour window from about 07:12 UTC on Oct 24, so tomorrow morning has room again. The script `evals/calibrate_critic.py` caps a run at what the repo count says is left.
- **Known gaps remaining:**
  - Whether a real free model obeys the fact-check and topic-fit rules (critic) and the topic rule (writer) is unproven until a live run or D2-B calibration.
  - The outer loop's measuring half has run for real; the planner and the write-and-critique half inside `run_outer` have only run against `MockLLM`. Both live posts have zero engagement, so there is no learning with signal for a plan to cite; the end-of-day check "the plan cites a learning" may need a post with real engagement or an openly planted example.
  - The critic passed a customer claim ("Beginners often notice the crust and crumb first") in `b0e71e`; the critic and writer prompts were tightened offline (`ca7af10`) and are unproven live. Flint spends about 3,500 tokens on a short post, so it is close to the 4,096-token truncation limit.
  - The 50 requests/day limit is unconfirmed for this account (issue 18; decided to stay at $0).
  - The GitHub schedule only measures (decision 4.11); it can never publish. The workflows are on `master` and one manual run succeeded; the scheduled run has not happened yet.
  - The Oct 23 calibration was partial (7 of 10, n = 7, one model); it is superseded by the complete Oct 24 runs (n = 10, still one model). Known script limits: a model that rejects `temperature` costs one extra request per draft; one draft using its own 4-request budget stops the whole run; a rerun re-spends every request (no reuse of earlier scores); two runs at once are not locked against.
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
| `3d96fe7` | feat: critic checks claims against the brief and planned post (Day 2 item (b)) | yes (merged, PR #1) |
| `c70e643` | docs: record decision to stay at $0 free tier | yes (merged, PR #1) |
| `ffe39e1` | fix: keep drafts on the planned topic (writer `TOPIC_RULE`, critic `TOPIC_FIT`) | yes (merged, PR #1) |
| `fc3abf0` | fix: skip a model that returns 404 for the rest of the run | yes (merged, PR #1) |
| `c26f11f` | feat: run-wide request budget, long-lived lock option and tool results as data | yes (merged, PR #1) |
| `5b60760` | feat: measure published posts and save a learning for each | yes (merged, PR #1) |
| `975da5f` | feat: weekly planner, plan state and daily request guard | yes (merged, PR #1) |
| `fa24b3e` | feat: outer loop and run_outer script | yes (merged, PR #1) |
| `d03dc07` | data: today's live post and run traces | yes |
| `8c36255` | docs: update handoff for Day 2 progress, model chain and outer loop | yes |
| `3f4d25a` | fix: keep the head and the tail of long trace summaries (issue 31) | yes (merged, PR #1) |
| `ca7af10` | fix: stop the writer echoing the topic and the critic missing claims about customers | yes (merged, PR #1) |
| `43b7545` | docs: handoff for issue 31 fix, prompt tightening and the b0e71e run | yes (merged, PR #1) |
| `d447a21` | test: end-to-end failure-handling tests for the seven D2-C cases (`evals/test_failure_handling.py`) | yes (merged, PR #1) |
| `f9dff75` | ci: GitHub Actions workflows and deploy doc (D2-D) | yes (merged, PR #1) |
| `1c1faeb` | docs: handoff for D2-C, D2-D and the cron decision | yes (merged, PR #1) |
| `057db64` | Merge pull request #1 (`feat/hermes-runtime`) | yes (`master`) |
| `6d3a2a5`, `7c0accc` | data: first learnings from the live posts and the declined run (PR #2, merged) | yes (`master`) |
| `0963ce2` | data: scheduled run 39942468962 (made by the workflow bot, pushed to `master` directly) | yes (`master`) |
| `abb99c8` | feat: optional temperature on the OpenRouter client (PR #3) | yes (`master`) |
| `3368c0d` | feat: critic calibration script and the ten drafts to hand-score (D2-B) (PR #3) | yes (`master`) |
| `8723983` | fix: calibration run stops on a refused key and never loses scored drafts or a good report (PR #3) | yes (`master`) |
| `6dfef98` | Merge pull request #3 (`feat/critic-calibration`) | yes (`master`) |
| `6123c79`, `59658c1`, `549882d` | data: hand scores and the first real critic calibration run (partial); handoff; merge of PR #4 | yes (`master`) |
| `f809321` | ci: move checkout and setup-python to v7 (Node 24) (PR #5) | on `ci/actions-node24`, **PR #5 open** |
| `e983feb` | data: scheduled run 39951119176 (the bot's push from the test run of `run.yml` on the PR branch) | on `ci/actions-node24`, PR #5 |
| `695956c`, `1376a5b`, `794390b`, `7495575`, `8cbd74f` | Merges of PR #5 (Actions v7), #6 (Hermes writer runtime), #7 (dashboard, README, demo), #8 (complete calibration data) and #9 (result text) | yes (`master`) |
| `7136093` | data: scheduled run 40084089747 (bot, 09:59 UTC on Oct 24; event type unconfirmed) | yes (`master`) |
| `49aa031`, `a936a71` | fix: critic clarity middle anchor, and the merge of PR #10 | yes (`master`) |
| `74abe56`, `0033d85` | data: calibration run after the clarity change, and the merge of PR #11 | yes (`master`) |
| `284bf48` | data: real-model outer loop dry run (PR #13) | PR #13, merged by the user (merge commit not seen here) |

- Every commit is authored by the user's identity `z <jirroaeron@gmail.com>`, with no trailers.
- **Local only, not in git:** `docs/ISSUES_LOG.md` (listed in `.git/info/exclude`).
- **Untracked on purpose:** `data/runs/run_20261022_080056_bb7b95.json`, a P1 sample dry-run trace with no LLM calls. Keep it out of git so it never shows on the dashboard.
- **Scratch work from today lives outside the repo:** the model probe script and its traces are in the session scratchpad, not in `data/`. The 4 probe requests are therefore not counted by `quota.run_cap`.
- **Local `master` is stale** (it still points at the initial commit); `origin/master` is the real one. Branch from `origin/master` (`git checkout -b <name> origin/master`) and do not trust local `master`.
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
12. **Pull requests (Oct 23):** all work reaches `master` through a PR that the **user merges** (with a merge commit, not a squash, to keep per-commit history). Claude opens PRs and says plainly whether CI is green and whether the PR is good to merge, but does not merge. Data-only PRs (learnings, traces, calibration) are separate from code PRs. A code PR is read before merging, not only checked for green CI.
13. **Hand scores (Oct 23):** the calibration scores are the user's own except 6 numbers that Claude adjusted at the user's request, under one rule (change a number only where it contradicts the rubric's own wording; leave taste alone). The first pass is kept and every change is listed in `data/calibration/adjustments.md`; the report discloses it. Do not call the scores "all hand-scored".
14. **Evidence stages (Oct 24):** order A, B, F, D, C, E with a stop between stages; each stage gets a plan, a baseline, a change, offline verification and one live step, and every OpenRouter, Bluesky or GitHub call needs the user's go after the exact command, the expected request count and the remaining quota are shown (a status question is not a go). Success criteria are fixed before a live run and a miss is reported, not tuned away. Never run `run_post` or `run_outer` live with `--no-approve`. Live posts are run by the user in a real terminal.
15. **Stage B (Oct 24):** the real-model `run_outer` was a dry run with `--dry-run --no-approve` on a scratch copy of `data/`, run by Claude, at the user's choice (the alternative, a live run with approval on, was not chosen). Dry runs publish only to a `dryrun://` URI.
16. **Pull requests (Oct 24):** the merge commit rule still holds; data PRs stay separate from code PRs and from docs PRs. No attribution trailers (CLAUDE.md overrides any tool-suggested trailer).
17. **Oct 25 decisions:** stage D forces cases 3, 7 and 4 only (case 1 skipped); issue 39 gets the small prompt fix; issue 40 is documented, not tuned; the dashboard is hosted on Cloudflare; stage D evidence lives in `data/evidence/stage_d/`, outside `data/runs`, so the dashboard and quota count never mix it with real runs.

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
- [~] **(f) D2-A:** metrics, analyst, learnings, planner, outer loop (and issue 16, read-after-post). **Code complete and merged. The measuring half has run for real (`--measure-only`, Oct 23); the planner and the write-and-critique half have only run against mocks.**
  - `--dry-run` still makes real planner and writer calls, so it costs quota.
  - **Review of this code (Oct 23):** no architecture-rule violations. Two findings fixed with tests and mutation checks: the planner now cites only learnings with signal (while every learning is "not enough data" no citation is required), and `run_outer()` itself refuses approval-off for a live run.
  - **Design note:** with approval mandatory, an unattended run writes a draft nobody can approve, so the post is carried forward and the requests are wasted (D2-D, decision 4.7).
  - The first real outer run is also the first real planner and analyst call; expect to find prompt problems.
- [~] **(g) D2-B, D2-C, D2-D:**
  - **D2-B** critic calibration: **tool built, reviewed twice (by Claude and by an independent reviewer) and merged (PR #3); first real run partial on Oct 23** (7 of 10 drafts, PR #4). **Done Oct 24:** a complete run of all 10 (agreement 6 of 10) and one rubric fix measured with a second complete run (agreement 7 of 10, clarity error 1.30 to 1.10; the pre-set criterion met narrowly, one draft, within noise; PRs #10 and #11). d03, d06 and d10 are still lenient, so the clarity problem is not fixed.
  - **D2-C** failure tests: **done** (`d447a21`, 12 tests, mutation-checked; no code bugs surfaced). Forcing each failure by hand against the real system is not done.
  - **D2-D** deploy: **done and run once.** Workflows merged, four repository secrets set (names only: `BLUESKY_APP_PASSWORD`, `BLUESKY_HANDLE`, `OPENROUTER_API_KEY`, `OPENROUTER_MODELS`), CI green on every PR, one manual run green. The first scheduled run (06:17 UTC, Oct 24) is the remaining proof. Not done: the trace page deploy.
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
- [x] `get_metrics` against real Bluesky: harness-side `fetch_metrics`, `measure.py` and not-found strikes (issue 16). Read live on Oct 23 for both posts (zero engagement). The not-found path (a very fresh post) is still only tested with a fake client.
- [~] `agents/analyst.py` ("not enough data" on zero or low engagement): done offline
- [~] `agents/planner.py` (reads learnings, cites one that has signal, harness checks and retries once): done offline
- [~] `loops/outer.py` (plan, inner loop, guardrails, publish, measure, learn; `--measure-only`; run summary; decision 4.3 applied): done offline
- [ ] 3-5 more real posts (2 done; with the 60-minute gap this takes about 3+ hours of wall time)

**Block 2: prove the critic (D2-B)**
- [x] 10 drafts (6 normal, 4 deliberately bad) in `data/calibration/drafts.csv`, hand-scored (34 of 40 numbers as entered, 6 adjusted; see decision 4.13)
- [x] `evals/calibrate_critic.py` built, reviewed and merged (27 plus 25 tests; mutation-checked; temperature 0 via the client's new `temperature` setting)
- [x] First real run: 7 of 10 scored on Oct 23 (partial, `report.partial-...md`); a complete run of all 10 on Oct 24 is `data/calibration/report.md` (`run_20261024_092334_1f3174`)
- [x] A complete run of all 10 (Oct 24, 13 requests, agreement 6 of 10)
- [~] One rubric fix with before and after numbers: done (#10, #11; agreement 6 to 7 of 10, clarity error 1.30 to 1.10, the pre-set criterion met narrowly, the gain is one draft and within noise). The clarity leniency is not fixed (d03, d06, d10 still lenient)

**Block 3: failure-handling tests (D2-C, tests 1-7 verbatim)**
- [x] Revision cap, JSON repair, rate cap, banned phrase, 429 fallback, publish ordering, prompt injection (`evals/test_failure_handling.py`, each driven through a whole `run_post` and checked in the trace or call log)
- [ ] Force each failure once by hand against the real system and confirm it in the trace (the tests use mocks; this step is not done)
  - D2-C forced by hand offline with scripted models (MockLLM; case 6 used the real OpenRouterLLM with a fake HTTP transport); the real harness, guardrails, trace and dry-run publish path ran. Real-model forcing is NOT done.

**Block 4: deploy (D2-D)**
- [x] `.github/workflows/run.yml` (cron 06:17 UTC assumed, `workflow_dispatch` with `dry_run`, Python 3.11, concurrency group, 20-minute timeout, commits `data/`); the schedule is measure-only (decision 4.11). One manual run green on Oct 23; the scheduled run is not yet seen
- [x] Separate CI workflow running pytest on every push and PR: `ci.yml`, green (536 tests on Oct 24, Ubuntu, Python 3.11)
- [x] `docs/DEPLOY.md` written; merged to `master`, four repository secrets added, one manual run done
- [~] **Scheduled run: unconfirmed.** A commit `data: scheduled run 40084089747` (author `autopilot[bot]`) landed on `master` at 09:59 UTC on Oct 24, but its event type is not confirmed (a manual dispatch uses the same message): read the Actions log. Earlier note: at 08:33 UTC `gh run list --workflow run.yml` showed no `schedule` run, only the two Oct 23 manual runs. The cron is on `master`. Cause not diagnosed (GitHub does not guarantee scheduled runs). Not triggered by hand. Check again after 06:17 UTC on Oct 25.
- Node 20 warning: fixed in PR #5 (open). `checkout` and `setup-python` are bumped to v7, which run on Node 24; CI is green, the Node 20 annotation is gone, and the data-push step was tested by dispatching `run.yml` from the PR branch (green, the bot's push worked). One leftover notice, the `ubuntu-latest` migration to Ubuntu 26, did not affect any run. A CI run with 0 jobs on that branch came from the bot's push, not from the code (ISSUES_LOG 9.11).
- [ ] Trace page deployed (Cloudflare Pages or Vercel)

**Block 5: Tier A runtime (P2, our addition)**
- [ ] P2: Hermes runtime behind the proxy, time-boxed to about 2 hours, *after the first live post* (decision 4.2). Design in section 9.

**End-of-day checks**
- [ ] The second run's plan cites a learning from the first (may need real engagement; see Known gaps)
- [~] **Scheduled run: unconfirmed.** A commit `data: scheduled run 40084089747` (author `autopilot[bot]`) landed on `master` at 09:59 UTC on Oct 24, but its event type is not confirmed (a manual dispatch uses the same message): read the Actions log. Earlier note: at 08:33 UTC `gh run list --workflow run.yml` showed no `schedule` run, only the two Oct 23 manual runs. The cron is on `master`. Cause not diagnosed (GitHub does not guarantee scheduled runs). Not triggered by hand. Check again after 06:17 UTC on Oct 25.
- [x] Tests pass locally and in GitHub Actions (414 on Oct 23, 536 on Oct 24)

### Day 3 (Sat Oct 24): polish, record, rehearse
- [ ] **D3-A** dashboard (overview, posts, learnings, trace view first) plus `scripts/export_dashboard_data.py`; check on phone and laptop
- [ ] **D3-B** `README.md` and `docs/DEMO.md` (with a planted bad brief that triggers a critic rejection and a guardrail block)
- [ ] Record the backup demo video; rehearse twice; Q&A prep
- [-] **D3-C** Scout (optional; first item on the PDF's cut list)

### Review prompts (before every merge)
- [ ] R1 diff review
- [ ] R2 explain-it on each module
- [ ] R3 adversarial tests
- [x] R4 secret scan of the whole repo history: done Oct 23 across all 40 commits on every branch. Exact-value check of the real API key and app password: 0 matches; the only secret-shaped strings are test fixtures and a code comment; no `.env`, key or credential file was ever committed. Not leaks, but worth a decision before the repo is ever made public: a local path in this handoff, the author email on every commit, and the Bluesky DID in tracked data files.
- Done as it went: independent reviews of `feat/hermes-runtime` (Oct 22), of the link-facet code, of the outer loop (Oct 23), and of the calibration script (Oct 23, by a fresh reviewer who saw only the code)

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
| 36 | The calibration script, as first written, kept asking for every remaining draft after a refused key (5 drafts made 5 failing calls) and a failed rerun overwrote the report of a complete run; it also lost scored drafts on Ctrl+C, a trace write error or an unexpected error, and crashed on Excel quirks (comma-only rows, a non-UTF-8 save), a full disk or an ASCII-only console. A test of ours also assumed the shipped CSV is blank, which would have failed once scores were committed | **Fixed** (`8723983`, PR #3): stops on a refused key, partial reports go to `report.partial-<run>.md`, 25 more tests, each fix mutation-checked; an independent reviewer found no further serious bug |
| 37 | **Calibration finding (partial on Oct 23, n = 7; superseded by the complete Oct 24 runs, see the Oct 24 update):** the critic is too lenient on d03 and d06 (all 5s against the user's 5/3/4/4 and 4/3/4/5) and its clarity scores run high (mean absolute error 1.29); it agreed that the deliberately bad drafts fail | Partly addressed (Oct 24): complete runs done and one rubric fix measured (pre-set criterion met narrowly, one draft, within noise); d03, d06 and d10 are still lenient, so not fixed |
| 38 | `quota.run_cap` counts only traces under `data/runs`, so requests made outside it (the 4 model-probe requests on Oct 23) are not counted; the 50 requests/day limit is also unconfirmed (issue 18) | Open, low: subtract known uncounted requests by hand, and keep a margin (the calibration run was capped at 14, not the 18 the count showed) |
| 39 | **Planner angles are invented sensory claims** (stage B, `run_20261024_114318_baec64`: "crust that cracks like leather"). They become the planned post, which the critic's fact check treats as supported, so an unsupported claim passes through the plan | **Fixed offline** (#15, Oct 25): the planner's `ANGLE_RULE`; the critic and writer take facts only from the brief or the planned post's topic. Real-model behavior unproven; the planner's topic is still trusted |
| 40 | The critic still gives clarity 5 to a draft with a scene, an aside and an invitation (d03/d06 pattern), seen again in the stage B draft | **Closed as a documented limitation** (Oct 25, decision 4.17): further tuning on the same 10 drafts would overfit |
| 43 | **The free writer overshoots the length limit and the one repair often stays over 300** (Oct 25: 4 of 8 repairs failed at 391, 303, 402 and 312 characters; each failed attempt cost 3-4 requests) | **Fixed offline** (#17): the repair asks for 240; unproven live |
| 44 | **A Bluesky call can time out after the harness sends the post** (`103042_bfa092`, `InvokeTimeoutError`) | **Handled as designed**: the pending row kept counting; the PDS showed no post; settled `failed` by hand per section 8. Consider a short automatic PDS check before reporting "outcome unknown" (next step) |
| 42 | **The critic misses invented facts and pressure on real drafts** (Oct 25): "10am-1pm" in `f232f7`, crust sounds and looks in `666dc2`, "You'll notice how the dough should feel slightly tacky" and "still has a few seats left—book today" in stage D case 4, all scored policy_risk 5 | Open, documented: human approval caught each one; approval stays mandatory |
| 41 | A trace outside `data/runs` is not counted by `quota.run_cap`: after a scratch-folder run the repo count reads low until its trace is copied in (seen on Oct 24: 32 shown, 45 spent) | Open, low: merge and pull the trace PR, or copy the trace in, before counting |

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
- **GitHub repository secrets** (set Oct 23 from `.env`, values never printed): the same four names. To change one, `printf '%s' "$value" | gh secret set NAME`, stripping quotes and any Windows `\r` first. `gh` is installed and logged in as `kkazei`.
- **Running the calibration:** `.venv311/Scripts/python.exe -m evals.calibrate_critic --check` shows the plan and the request cap with no model calls; without `--check` it runs for real (about 10 to 14 requests). `--max-requests N` lowers the cap. A complete run writes `data/calibration/report.md`; an incomplete one writes `report.partial-<run>.md` and leaves `report.md` alone. Do not run a rehearsal without `AUTOPILOT_DATA_DIR` pointing at a scratch folder, or traces land in `data/runs`.
- **GitHub CLI checks used on Oct 23:** `gh pr checks <n>`, `gh run watch <id> --exit-status`, `gh workflow run run.yml --ref master -f dry_run=false`, and `gh run view <id> --log`.
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
- **Next actions (as of 11:45 UTC, Oct 23; historical, superseded by the Oct 24 list in section 2):**
  1. **Merge PR #4** (user): data and this handoff, CI green. Then `git pull` on a branch from `origin/master`.
  2. **Offline leftovers: done (Oct 23).** The scripted dry run, the full-history secret scan, local `master` fast-forwarded and the merged local branches deleted, the Actions bump (PR #5) and the local ISSUES_LOG (sections 9.1 to 9.13). **Spend no more quota today** (about 47 of 50 used). Merge PR #5 when ready.
  3. **Tomorrow morning, first thing, with a fresh quota:** (a) check the 06:17 UTC scheduled run in the Actions tab; (b) run the complete calibration (`--check` first, then for real; do it before anything else so the free models are least busy); (c) make the rubric fix and rerun once more for the before and after numbers, if quota allows; (d) one or more live posts in a real terminal (`run_post`, never with the `!` prefix, never with a placeholder topic); (e) the first real planner run through `run_outer`; (f) force each D2-C failure by hand.
  4. **Decide whether to cut P2** (the Hermes runtime). The pipeline already calls OpenRouter directly, which was the plan's own fallback.
  5. **Day 3 (Oct 24)** is mostly offline: D3-A dashboard and `scripts/export_dashboard_data.py` (plus the trace page deploy), D3-B README and `docs/DEMO.md`, the backup video, rehearsal. If the free-model pool is as shaky tomorrow as today, build the demo around what already works (two real posts, the learnings, the green workflow run, the partial calibration) and say plainly what is partial.
  6. Item (d) stays decided: stay at $0 and ration requests.
- **Local ISSUES_LOG (not in git) is up to date through Oct 23** (new section 9, entries 9.1 to 9.13, and the earlier statuses corrected). It mixes first person and the user's voice in a few places and may want rewording.
- **Process note:** a status question is not a go-ahead. Do not start editing code until the user says so.
