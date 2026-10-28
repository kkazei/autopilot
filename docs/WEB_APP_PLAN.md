# Autopilot web app: plan

A private web app that replaces the local Gradio app, at $0. Decided 2026-10-28; target is two days of build.

## Decisions

| Question | Decision |
|---|---|
| Who uses it | Only the owner. GitHub login, allowlisted to `kkazei`. |
| Where the code lives | `web/` in this repo (Next.js). The Python backend stays in this repo too. |
| Hosting | Next.js on **Vercel Hobby**. Python backend (FastAPI) on a **private Hugging Face Space** (Docker, free CPU). Render is the fallback. |
| Data | **Neon Postgres** is the source of truth. `data/` is imported once; the git Save/Pull cycle retires with Gradio. |
| How the database meets the harness | A **sync layer** (`harness/db_sync.py`): a hosted run takes one Postgres lock, pulls the state into a working folder, runs the unchanged harness on files, and pushes the result back. Traces are pushed live during the run. |
| Publishing | Every post from the web needs the owner's approval. The harness gates (schema, brand safety, rate cap) are unchanged. |
| Model requests | Hard cap of **45 per 24 hours** (`harness/quota.py`), shared by every way of running. |
| Design | A fresh design pass before the screens are built. |

## Shape

```
Browser ──▶ Next.js on Vercel (web/)   GitHub login (kkazei only)
              │ reads                  │ run / approve (shared secret + HF token)
              ▼                        ▼
         Neon Postgres  ◀────────  FastAPI on a private HF Space
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
| 1 | 2. Backend | FastAPI on the Space (run, status, approve, health), shared-secret auth, Dockerfile; cron moves to `db_run`. |
| 2 | 3. Design | One direction, tokens, no exploration rounds. |
| 2 | 4. Web v1 | Login, plan and posts, learnings, approval queue, start and watch runs, trace viewer, quota meter. |
| later | 5. Cutover | Gradio and the web side by side for a few days, then retire Gradio and the data PR cycle. |

Until cutover, a local Gradio post is not in the database, so the hosted rate cap cannot see it: post from one place at a time,
and run `python -m scripts.db_import` after a local post (it only appends what the database lacks).

## Phase 0: the owner's checklist (about 20 minutes)

Never paste a secret into chat or a commit. Put each in `.env` locally and in the host's secret settings.

1. **Neon** (neon.tech, free plan): create project `autopilot`, region near you. Copy the connection string with
   **Connection pooling off** (the direct URL, host without `-pooler`). Put it in `.env` as `DATABASE_URL=...`.
   Then create a branch named `test` and put its direct URL in `.env` as `AUTOPILOT_TEST_DATABASE_URL=...`
   (the live store test drops its tables, so it must never point at the main branch).
2. **Hugging Face** (huggingface.co, free): create a **private** Space named `autopilot-api`, SDK **Docker**, hardware **CPU basic**.
   Create an access token with **write** scope for deploying, and a separate **read** token for Vercel to call the private Space.
3. **Vercel** (vercel.com, Hobby): sign in with GitHub. The project is created in Phase 4, pointed at `web/`.
4. **GitHub OAuth app** (GitHub, Settings, Developer settings, OAuth Apps, New): name `Autopilot`, homepage
   `http://localhost:3000`, callback `http://localhost:3000/api/auth/callback/github`. Keep the client id and secret for Phase 4;
   a second OAuth app for the Vercel URL is made once that URL exists.
5. When `.env` has `DATABASE_URL`, run the one-time import:
   `.venv\Scripts\python -m scripts.db_import`

## Known limits

- The Space sleeps after about 48 hours idle; the first request wakes it (about a minute). The web app shows a waking state.
- Neon suspends its compute after 5 idle minutes and wakes on connect (a few seconds).
- `data/runtime/mcp_calls.jsonl` and the calibration and evidence folders are not synced; they stay in git as evidence.
- Vercel Hobby is for non-commercial use, which fits a demo.
