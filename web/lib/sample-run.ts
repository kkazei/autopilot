// The shape of one real dry run (Oct 28, 2026) for the public page: timings, agents, models and short labels only.
// Prompts, drafts and model outputs are left out on purpose. Regenerate rather than hand-edit.
import type { TraceEvent } from "./parse";

export const SAMPLE_RUN: TraceEvent[] = [
  {
    "ts": "2026-10-28T14:00:54.573710Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "start",
    "summary_out": "approval on",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:00:54.578357Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "daily guard",
    "summary_out": "within the 45/day cap",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:00:54.581141Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "measure candidates",
    "summary_out": "nothing to measure",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:00:54.583590Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "measure",
    "summary_out": "nothing to measure",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:00:54.657742Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "select post",
    "summary_out": "next planned post",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:00:55.038022Z",
    "run_id": "example",
    "agent": "writer",
    "kind": "llm_call",
    "summary_in": "model call",
    "summary_out": "failed: HTTP 429",
    "ok": false,
    "model": "google/gemma-4-31b-it:free",
    "latency_ms": 376
  },
  {
    "ts": "2026-10-28T14:00:55.044133Z",
    "run_id": "example",
    "agent": "writer",
    "kind": "decision",
    "summary_in": "retry",
    "summary_out": "backoff 2.4s, then retry 2/3",
    "ok": true,
    "model": "google/gemma-4-31b-it:free",
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:00:57.674144Z",
    "run_id": "example",
    "agent": "writer",
    "kind": "llm_call",
    "summary_in": "model call",
    "summary_out": "failed: HTTP 429",
    "ok": false,
    "model": "google/gemma-4-31b-it:free",
    "latency_ms": 189
  },
  {
    "ts": "2026-10-28T14:00:57.677952Z",
    "run_id": "example",
    "agent": "writer",
    "kind": "decision",
    "summary_in": "retry",
    "summary_out": "backoff 3.7s, then retry 3/3",
    "ok": true,
    "model": "google/gemma-4-31b-it:free",
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:04.133367Z",
    "run_id": "example",
    "agent": "writer",
    "kind": "llm_call",
    "summary_in": "write draft",
    "summary_out": "draft written",
    "ok": true,
    "model": "google/gemma-4-31b-it:free",
    "latency_ms": 2758
  },
  {
    "ts": "2026-10-28T14:01:09.421111Z",
    "run_id": "example",
    "agent": "critic",
    "kind": "llm_call",
    "summary_in": "score draft",
    "summary_out": "voice 5 · clarity 5 · cta 5 · policy 5",
    "ok": true,
    "model": "google/gemma-4-31b-it:free",
    "latency_ms": 5281
  },
  {
    "ts": "2026-10-28T14:01:09.425429Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "inner loop",
    "summary_out": "passed on attempt 1",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:09.430520Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "check_length",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:09.434011Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "check_banned",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:09.437452Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "check_rate_cap",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:09.440967Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "check_duplicate",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.008802Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "require_approval",
    "summary_out": "approved",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.016313Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "re-check check_length",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.020626Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "re-check check_banned",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.024793Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "re-check check_rate_cap",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.029346Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "guardrail",
    "summary_in": "re-check check_duplicate",
    "summary_out": "pass",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.034569Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "tool_call",
    "summary_in": "publish_post",
    "summary_out": "dry run: published to dryrun://",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.039030Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "publish",
    "summary_out": "published (dry run)",
    "ok": true,
    "model": null,
    "latency_ms": null
  },
  {
    "ts": "2026-10-28T14:01:56.044166Z",
    "run_id": "example",
    "agent": "harness",
    "kind": "decision",
    "summary_in": "run_summary",
    "summary_out": "exit 0 · done",
    "ok": true,
    "model": null,
    "latency_ms": null
  }
];
