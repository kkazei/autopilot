# Deploying Autopilot on GitHub Actions

Two workflows live in `.github/workflows/`:

| Workflow | Runs when | Does |
|---|---|---|
| `ci.yml` | every push and pull request | installs `requirements.txt` on Python 3.11 and runs `pytest -q` (offline, no secrets) |
| `run.yml` | daily at 06:17 UTC, or by hand | `python -m scripts.run_outer --measure-only`, then commits anything new under `data/` |

## What the schedule does, and does not do

The scheduled run **only measures**: it reads likes, reposts and replies on posts at least 2 hours old, saves a learning for each, and
stops. It writes no drafts and publishes nothing. Publishing needs a human to answer `Publish this post? [y/N]`, a runner has no
keyboard, and approval stays mandatory (HANDOFF decision 4.7). **Live posts are made on your own machine.**

A manual run with `dry_run = true` does the whole loop (plan if nothing is waiting, write, critique, guardrails) and publishes to a
`dryrun://` URI. It spends model requests (about 3 to 4 from the free quota) and saves no plan state and no learning.

## One-time setup

1. **Merge to `master`.** GitHub runs scheduled workflows, and shows the "Run workflow" button, only for workflow files on the default
   branch. Until `.github/workflows/` is on `master`, nothing here runs. (`ci.yml` runs on any branch with no merge.)
2. **Add the four repository secrets**: repository, Settings, Secrets and variables, Actions, New repository secret.

   | Name | Value |
   |---|---|
   | `OPENROUTER_API_KEY` | your OpenRouter key (the value in `.env`) |
   | `OPENROUTER_MODELS` | the comma-separated `:free` model ids (the value in `.env`) |
   | `BLUESKY_HANDLE` | the account handle |
   | `BLUESKY_APP_PASSWORD` | the app password, not the account password |

   With the GitHub CLI, you can copy each value from `.env` without printing it:
   `grep '^OPENROUTER_API_KEY=' .env | cut -d= -f2- | gh secret set OPENROUTER_API_KEY`
   (repeat with the other three names). Secrets are masked in logs, and the workflow never echoes them: its check step prints only
   the *name* of a missing secret, and the job fails if any of the four is empty.
3. **Make sure CI can see your posts.** `approved.jsonl` and the plan state are read from the repository, so push them after every
   local post: `git add data/ && git commit -m "data: ..." && git push`. A post that was never pushed is invisible to the runner.

## First manual run

1. Actions tab, "Autopilot run", Run workflow, choose `master`, leave `dry_run` unchecked, Run.
2. Expect: steps go green; the log shows `model requests: N in the last 24 hours` and either `measure: saved learnings for ...` or
   `measure: <id>: not yet measurable`; if anything new was written, a commit `data: scheduled run <run id>` appears.
3. Then try `dry_run` checked once, to see the full loop run without publishing.

Equivalent CLI: `gh workflow run run.yml --ref master -f dry_run=false`.

## Day to day

- Before posting locally, `git pull` first, so you have the learnings the runner saved.
- A scheduled run can find nothing to do. That is a green run, not a failure.
- To stop the schedule: Actions tab, "Autopilot run", the `...` menu, Disable workflow.
- If a run fails after `git commit`, the push step fails loudly (a rebase conflict, for example). Nothing is overwritten; fix it locally.

## Assumptions and deviations from the build plan

- **06:17 UTC** is an assumption: off the hour, when scheduled jobs queue, and later than 2 hours after a post made the evening before.
- The plan's `python -m loops.outer` does not exist here; the entry point is `python -m scripts.run_outer`.
- **Hermes is not installed on the runner.** The workflow runs with `AUTOPILOT_WRITER_RUNTIME` unset, which means `direct`: OpenRouter is called straight from the harness. Running the writer through Hermes (`AUTOPILOT_WRITER_RUNTIME=hermes`) is a local option; it needs the `hermes` CLI on the PATH, and the scheduled run only measures, so it has no writer to switch.
- The schedule does not publish, which is the choice made on Oct 23 for the cron-versus-approval conflict. A posting cron would need
  a deliberate change to decision 4.7, or a pre-approved drafts queue that does not exist yet.
- Pushes made with the built-in `GITHUB_TOKEN` do not trigger other workflows, so the data commit does not start a CI run.
- The free-tier guard (`harness/quota.py`) counts `llm_call` events in `data/runs/`. The runner's traces are committed back, so the
  count stays correct across local and CI runs, as long as local traces are pushed too.
