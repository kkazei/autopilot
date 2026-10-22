# Autopilot: project rules

## What this is

Autopilot is an autonomous marketing agent system for a fictional small business. It plans a week of social posts, writes and critiques drafts, publishes to Bluesky, reads engagement, and feeds learnings into the next plan. Agents run on Hermes Agent with free OpenRouter models. All tools sit behind one MCP server.

## Stack and constraints

- Python 3.11+, pydantic v2, pytest. Everything must run at $0: no paid APIs.

- LLMs: OpenRouter free models (":free" ids) with tool calling and at least 64K context. Models are configured in one place (harness/[llm.py](http://llm.py)) as an ordered fallback chain. On HTTP 429 or timeout, back off, then try the next model.

- Channel: Bluesky via the atproto package, using an app password from environment variables.

- Secrets come only from environment variables or .env (git-ignored). Never hard-code, log or print them.

## Architecture rules (do not break)

1. The orchestrator in loops/ owns control flow. Agents never decide to publish.

2. Only harness code calls the publish\_post tool, and only after schema validation, brand-safety checks, the rate cap and (if enabled) human approval all pass.

3. Every LLM call and tool call is written to the trace through harness/[trace.py](http://trace.py).

4. Every agent output is validated against a pydantic model in harness/[schemas.py](http://schemas.py). On invalid JSON: one repair attempt, then fail cleanly and log it.

5. The critic's passed flag is computed by the harness from the scores and a threshold, never taken from the model.

6. Inner loop: at most 3 revisions, then escalate to human review. No unbounded loops anywhere.

7. Each agent role has its own tool allowlist: planner and analyst are read-only, the writer only gets get\_brand\_brief, the critic gets no tools.

## Working style

- Small, typed, readable functions. Docstrings explain why, not what.

- Write or update tests for any change in harness/ or loops/. Run pytest before saying you are done.

- Do not add dependencies without saying why. Prefer the standard library.

- Before large changes, state a short plan. After changes, list the files touched and how you verified them.

- If something is ambiguous, ask instead of guessing.

## Definition of done for any task

Tests pass, no secrets in the diff, trace output verified by running the code once, and a 3-line summary of what changed.