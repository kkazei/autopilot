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
- `dashboard/`: a static, read-only page (overview, posts, learnings, trace). `evals/` and `tests/`: the tests.

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
python -m scripts.demo_bad_brief         # replay the planted-bad-brief demo with scripted models (docs/DEMO.md)
python -m scripts.export_dashboard_data  # build dashboard/data.json; then open dashboard/index.html in a browser
```

Things that call the real free models (they spend the free daily quota, about 2 to 9 requests for one post):

```
python -m scripts.run_post --topic "<a real, specific topic>" --goal click --dry-run   # publishes to a dryrun:// address
python -m scripts.run_post --topic "<a real, specific topic>" --goal click             # asks you before posting
```

Run these in a real terminal: the approval prompt needs a keyboard. Models are listed in `OPENROUTER_MODELS`; on a 429 or a timeout the client backs off and tries the next one. The free models are unstable (some have been retired, others rate-limit in bursts), so expect to adjust that list.

**Hermes writer runtime (opt-in).** By default every agent calls OpenRouter straight from the harness. With `AUTOPILOT_WRITER_RUNTIME=hermes` (and the `hermes` CLI installed), the writer's first call of each attempt runs through [Hermes Agent](https://github.com/NousResearch/hermes-agent) behind a harness-owned LLM proxy that holds the key; a cross-check of the proxy, Hermes's output and the tool call log fails closed, and anything it cannot trust falls back to the direct chain. Repairs, the critic and the other roles always run direct. One live run so far: Hermes answered and the cross-check passed, but its draft was over the length limit, so the post was written by the harness's direct repair.

## What is proven, and what is partial

**Proven for real**
- 2 live posts on Bluesky, each human-approved, with full traces.
- The measuring half of the outer loop against the live account (it read both posts and saved a learning for each; engagement was zero, so both learnings say "not enough data").
- The deploy workflow ran once by hand and succeeded; CI runs the tests on every pull request.
- The harness's failure handling (revision cap, JSON repair, rate cap, banned phrase, 429 fallback, prompt injection, publish ordering) in automated tests, and once more by hand with scripted models.

**Partial or not proven yet**
- **Critic calibration is complete, and the critic is too lenient:** all 10 drafts scored by one model, which agreed with the hand scores on 6 of 10 and passed four drafts that should fail (d03, d06, d08, d10). No rubric fix has been made or re-measured.
- **The scheduled run is unproven:** the 06:17 UTC GitHub run did not fire on Oct 24. It only measures and can never publish.
- **The planner inside the outer loop has not run live:** only against mocks. There is no learning with real engagement for it to cite yet.
- **Real-model failure forcing is not done:** the failures were forced with scripted models, so this shows the harness reacts correctly, not that a real free model misbehaves in those ways.
- The 50-requests-a-day free limit is assumed, not confirmed for this account.

Details and decisions: `docs/HANDOFF.md`. To see it in action: `docs/DEMO.md`. Deploying the workflow and the dashboard: `docs/DEPLOY.md`.
