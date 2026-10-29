# Autopilot web app: plan

A private web app that replaces the local Gradio app, at $0. Decided 2026-10-28; target is two days of build.

**Status (2026-10-29): live.** Phases 0 to 4 are done: https://autopilot-kkazei.vercel.app (public page at `/`, the owner's
panel behind sign-in), the backend on Render, Neon as the source of truth, and the daily job on `db_run`. Built on top of
v1: local time zones, motion, a run timeline, topic posts, password sign-in, a public landing page, Learnings grouped by
post, Measure now, matte navigation, a theme switch and runs described in plain words (PRs #36 to #46). Phase 5 is done: the Gradio app and the
static dashboard were removed on Oct 29 and archived in the `local-app-final` release.

## Decisions

| Question | Decision |
|---|---|
| Who uses it | Only the owner. GitHub login, allowlisted to `kkazei`. |
| Where the code lives | `web/` in this repo (Next.js). The Python backend stays in this repo too. |
| Hosting | Next.js on **Vercel Hobby**. Python backend (FastAPI) on **Render's free web service** (Docker). Hugging Face was the first pick, but Docker Spaces became paid (2026-10-28). |
| Data | **Neon Postgres** is the source of truth. `data/` is imported once; the git Save/Pull cycle retires with Gradio. |
| How the database meets the harness | A **sync layer** (`harness/db_sync.py`): a hosted run takes one Postgres lock, pulls the state into a working folder, runs the unchanged harness on files, and pushes the result back. Traces are pushed live during the run. |
| Publishing | Every post from the web needs the owner's approval. The harness gates (schema, brand safety, rate cap) are unchanged. |
| Model requests | Hard cap of **50 per 24 hours** (`harness/quota.py`), shared by every way of running (45 until Oct 29, while the local app shared the key). |
| Design | A fresh design pass before the screens are built. |

## Shape

```
Browser ──▶ Next.js on Vercel (web/)   GitHub login (kkazei only)
              │ reads                  │ run / approve (shared secret)
              ▼                        ▼
         Neon Postgres  ◀────────  FastAPI on Render (free web service)
         (source of truth)          loops/ + harness/, holds the OpenRouter and Bluesky secrets
              ▲
              └── GitHub Actions cron (daily measure) via scripts/db_run.py
```

The web app never publishes. Approve calls the backend, which answers the harness's approval prompt; publish() still re-runs every
guardrail before it posts (architecture rules 1 and 2).

## Phases

| Day | Phase | What |
|---|---|---|
| 1 | 0. Accounts | The owner's checklist below. |
| 1 | 1. Database layer | `harness/db_sync.py`, `harness/db_store.py`, `scripts/db_import.py`, `scripts/db_run.py`. |
| 1 | 2. Backend | FastAPI on Render (run, status, approve, health), shared-secret auth, Dockerfile, render.yaml; cron moves to `db_run`. |
| 2 | 3. Design | One direction, tokens, no exploration rounds. |
| 2 | 4. Web v1 | Login, plan and posts, learnings, approval queue, start and watch runs, trace viewer, quota meter. |
| later | 5. Cutover | Gradio and the web side by side for a few days, then retire Gradio and the data PR cycle. Done Oct 29 (release `local-app-final`). |

Anything written to the local `data/` files is not in the database, so the hosted rate cap cannot see it: post only from
the web app or through `scripts.db_run`. (Should it ever happen, `python -m scripts.db_import` appends what the database lacks.)

## Phase 0: the owner's checklist (about 20 minutes)

Never paste a secret into chat or a commit. Put each in `.env` locally and in the host's secret settings.

1. **Neon** (neon.tech, free plan): create project `autopilot`, region near you. Copy the connection string with
   **Connection pooling off** (the direct URL, host without `-pooler`). Put it in `.env` as `DATABASE_URL=...`.
   Then create a branch named `test` and put its direct URL in `.env` as `AUTOPILOT_TEST_DATABASE_URL=...`
   (the live store test drops its tables, so it must never point at the main branch).
2. **Render** (render.com, free): sign up with GitHub and give it access to the `autopilot` repository. The service itself is
   created from `render.yaml` in Phase 2.
3. **Vercel** (vercel.com, Hobby): sign in with GitHub. The project is created in Phase 4, pointed at `web/`.
4. **GitHub OAuth app** (GitHub, Settings, Developer settings, OAuth Apps, New): name `Autopilot`, homepage
   `http://localhost:3000`, callback `http://localhost:3000/api/auth/callback/github`. Keep the client id and secret for Phase 4;
   a second OAuth app for the Vercel URL is made once that URL exists.
5. When `.env` has `DATABASE_URL`, run the one-time import:
   `.venv\Scripts\python -m scripts.db_import`

## Phase 2: wiring the backend

The backend is `backend/app.py`, a FastAPI wrapper around the local app's Controller. Every run is wrapped in
`db_sync.hosted_data_dir`. Routes: `GET /health` (open), and with the `X-Autopilot-Secret` header `GET /status`,
`POST /runs` (`next`, `topic`, `plan`, `measure`), `POST /approvals/{id}` and `POST /posts/{id}/requeue`.

1. **A backend secret.** Generate one and keep it in `.env` as `AUTOPILOT_BACKEND_SECRET` (Vercel gets it in Phase 4):
   `.venv\Scripts\python -c "import secrets; print(secrets.token_hex(32))"`
2. **GitHub secret for the cron**: `grep '^DATABASE_URL=' .env | cut -d= -f2- | gh secret set DATABASE_URL`
3. **Render** (after the PR is on master): New, Blueprint, pick the `autopilot` repository. Render reads `render.yaml` and asks for
   the six values: `OPENROUTER_API_KEY`, `OPENROUTER_MODELS`, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `DATABASE_URL`,
   `AUTOPILOT_BACKEND_SECRET` (copy them from `.env`). Do not add `AUTOPILOT_WRITER_RUNTIME`: the backend runs the direct
   OpenRouter path, like the cron. Later pushes to master that touch backend code redeploy it.
4. Check it: `curl https://autopilot-api.onrender.com/health` (the exact URL is on the service page) returns `{"ok":true}`.

From this phase the cron reads and writes Postgres and no longer commits `data/`.

## Phase 4: the web app on Vercel

The app is `web/` (Next.js 16, App Router). It reads Neon directly and sends runs, approvals and requeues to the backend
through `/api/actions`, which only the signed-in owner can call, and only from the app's own origin.

1. **GitHub OAuth apps** (GitHub, Settings, Developer settings, OAuth Apps). One for local dev: homepage `http://localhost:3000`,
   callback `http://localhost:3000/api/auth/callback/github`. One for production, made after step 2 gives the Vercel URL:
   homepage `https://<project>.vercel.app`, callback `https://<project>.vercel.app/api/auth/callback/github`.
2. **Vercel** (vercel.com, Hobby): Add New, Project, import `kkazei/autopilot`, set **Root Directory** to `web`. Framework is
   detected as Next.js. Add these environment variables (Production), then Deploy:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon direct URL (same as `.env`) |
   | `AUTOPILOT_BACKEND_URL` | the Render service URL, e.g. `https://autopilot-api-xxxx.onrender.com` |
   | `AUTOPILOT_BACKEND_SECRET` | same as `.env` and Render |
   | `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` | from the production OAuth app |
   | `NEXTAUTH_SECRET` | a new random value: `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"` |
   | `NEXTAUTH_URL` | `https://<project>.vercel.app` |
   | `AUTH_ALLOWED_LOGIN` | `kkazei` |
   | `AUTH_PASSWORD_HASH` | optional: enables username + password sign-in (the username is `AUTH_ALLOWED_LOGIN`). Make it with `cd web && node scripts/hash-password.mjs` in your own terminal |

3. Local dev: copy `web/.env.example` to `web/.env.local`, fill it from `.env` and the local OAuth app, then
   `cd web && npm install && npm run dev`.

Password sign-in locks a username after 5 wrong passwords in 15 minutes (an IP after 10), counted in the `auth_failures`
table, the only table the web app writes. GitHub sign-in is unaffected, so a lockout never shuts the owner out.

## Known limits

- Render's free service sleeps after 15 idle minutes; the first request wakes it (about a minute). The web app shows a waking
  state, and its status polling keeps the service awake while a run or an approval is open. 512 MB of memory.
- Neon suspends its compute after 5 idle minutes and wakes on connect (a few seconds).
- `data/runtime/mcp_calls.jsonl` and the calibration and evidence folders are not synced; they stay in git as evidence.
- Vercel Hobby is for non-commercial use, which fits a demo.
