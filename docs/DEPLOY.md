# Deploying Autopilot

Everything runs on free tiers. Four pieces, each deployed from `master`:

| Piece | Where | Deploys | Does |
|---|---|---|---|
| Web app (`web/`) | Vercel Hobby | on every push to `master` | the public page and the owner's control panel; reads Neon, sends actions to the backend |
| Backend (`backend/`) | Render free web service, Docker (`render.yaml`) | on pushes to `master` that touch the Python code | runs the harness for the web app, one run at a time |
| Database | Neon free Postgres (us-east-1) | n/a | the source of truth: plans, posts, learnings, traces |
| Daily job and CI (`.github/workflows/`) | GitHub Actions | from `master` | `run.yml` measures every day; `ci.yml` runs the tests |

First-time setup, with every environment variable and where its value comes from, is in `docs/WEB_APP_PLAN.md`
(Phase 0, Phase 2 and Phase 4). This page is about how the pieces behave once set up.

## Secrets

Secrets live only in `.env` (git-ignored), and in each platform's own settings. Never in the repository, never in a log.

| Name | `.env` | Render | Vercel | GitHub Actions |
|---|---|---|---|---|
| `OPENROUTER_API_KEY`, `OPENROUTER_MODELS` | yes | yes | | yes |
| `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | yes | yes | | yes |
| `DATABASE_URL` (Neon, direct) | yes | yes | yes | yes |
| `AUTOPILOT_BACKEND_SECRET` | yes | yes | yes | |
| `AUTOPILOT_BACKEND_URL` | | | yes | |
| `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET`, `NEXTAUTH_SECRET`, `NEXTAUTH_URL`, `AUTH_ALLOWED_LOGIN` | | | yes | |
| `AUTH_PASSWORD_HASH` (optional; mark it Sensitive) | | | yes | |

To copy a value from `.env` into a GitHub secret without printing it:
`grep '^DATABASE_URL=' .env | cut -d= -f2- | gh secret set DATABASE_URL`. The daily job's first step prints only the
*name* of a missing secret and fails if any is empty.

Changing the model list means updating `OPENROUTER_MODELS` in three places: `.env`, Render, and the GitHub secret.

## The daily job (`run.yml`)

Runs `python -m scripts.db_run --measure-only` every day at 06:17 UTC (GitHub starts scheduled jobs hours late; it has
run between 10:58 and 13:00 UTC). It pulls the state from Neon, reads likes, reposts and replies on posts at least
2 hours old, saves a learning for each, pushes back, and stops. It writes no drafts and publishes nothing, and it commits
nothing to the repository.

- **Measure now** in the web app (Control and Learnings) runs the same measure-only run through the backend, on demand.
- A manual run with `dry_run = true` does the whole loop and publishes to a `dryrun://` address: Actions, "Autopilot run",
  Run workflow. CLI: `gh workflow run run.yml --ref master -f dry_run=true`.
- The job and the backend take the same Postgres advisory lock, so they never overlap: a job that starts while a hosted
  run is going exits with code 6 and does nothing.
- A run that finds nothing to measure is a green run, not a failure.
- To stop the schedule: Actions, "Autopilot run", the `...` menu, Disable workflow.

## The backend (Render)

- Free services sleep after 15 idle minutes. The web app pings `/health` (no secret) to wake it and disables its run
  buttons until it answers, about a minute. While a run or an approval is open, the app's status polling keeps it awake.
- Every route except `/health` needs the `X-Autopilot-Secret` header. The run kinds are fixed in `backend/app.py`
  (`next`, `topic`, `plan`, `measure`); approval cannot be switched off from outside.
- A pending approval that gets no answer within 15 minutes, or a backend restart, counts as "not now": the post is
  carried forward and the lock is released.

## The web app (Vercel)

- Root directory `web`; Vercel detects Next.js. Every push to `master` deploys; pull requests get preview deploys.
- An environment variable change takes effect only on the next deploy: Deployments, the latest one, Redeploy.
- The public page `/` is static. Everything else needs the owner's sign-in.

## CI (`ci.yml`)

On every push and pull request: the Python suite on 3.11 (offline; no secrets, sockets blocked), then the web app's
tests, type check and production build (no secrets or database needed).

## Retired

The static dashboard (Cloudflare Workers Builds) and the local Gradio app were removed on Oct 29; both worked on the
`data/` files in git, which stopped updating when Neon became the source of truth. Their last version is the
[local-app-final](https://github.com/kkazei/autopilot/releases/tag/local-app-final) release. The Cloudflare Worker named `autopilot` is no longer built from this repository.
