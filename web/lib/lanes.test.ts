import assert from "node:assert/strict";
import { test } from "node:test";

import { toLanes } from "./lanes.ts";
import type { TraceEvent } from "./parse.ts";

const ev = (s: number, over: Partial<TraceEvent>): TraceEvent => ({
  ts: new Date(Date.UTC(2026, 9, 26, 14, 5, 0) + s * 1000).toISOString(), run_id: "r", agent: "harness", kind: "decision",
  summary_in: "x", summary_out: "y", ok: true, model: null, latency_ms: null, ...over,
});

test("one lane per agent in pipeline order, model calls spanning their latency", () => {
  const { lanes, total } = toLanes([
    ev(0, { summary_in: "run_outer", summary_out: "start" }),
    ev(4, { agent: "writer", kind: "llm_call", latency_ms: 3000, model: "google/gemma-4-31b-it:free", summary_out: "draft" }),
    ev(12, { agent: "critic", kind: "llm_call", latency_ms: 8000, ok: true }),
    ev(12, { kind: "guardrail", summary_in: "check_length | t", summary_out: "pass" }),
  ]);
  assert.deepEqual(lanes.map((l) => l.id), ["writer", "critic", "harness"]);
  const w = lanes[0].steps[0];
  assert.equal(w.tone, "model");
  assert.ok(Math.abs(w.start - 1) < 1e-9 && Math.abs(w.end - 4) < 1e-9);
  assert.equal(w.detail, "gemma-4-31b-it · 3000 ms");
  assert.ok(total >= 12);
});

test("the approval wait spans from the previous event to the answer, and failures are marked", () => {
  const { lanes } = toLanes([
    ev(0, { agent: "critic", kind: "llm_call", latency_ms: 300, ok: false, summary_out: "attempt 1/3 failed: HTTP 429" }),
    ev(10, { kind: "guardrail", summary_in: "check_duplicate | t", summary_out: "pass" }),
    ev(55, { kind: "guardrail", summary_in: "require_approval | t", summary_out: "pass" }),
  ]);
  const harness = lanes.find((l) => l.id === "harness")!;
  const wait = harness.steps.find((s) => s.tone === "wait")!;
  assert.ok(wait.end - wait.start >= 44, "a 45 s wait for the owner is one long bar");
  assert.equal(lanes.find((l) => l.id === "critic")!.steps[0].tone, "model-failed");
});

test("a burst of instant events does not pile onto one point", () => {
  const { lanes } = toLanes([ev(0, {}), ev(30, {}), ev(30, {}), ev(30, {})]);
  const s = lanes[0].steps;
  assert.ok(s[2].start >= s[1].end && s[3].start >= s[2].end);
  assert.deepEqual(toLanes([]), { lanes: [], total: 0 });
});
