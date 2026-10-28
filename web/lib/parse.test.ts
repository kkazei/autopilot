import assert from "node:assert/strict";
import { test } from "node:test";

import {
  countLlmCalls, latestCritique, latestGuardrails, parseApprovalPrompt, parseCritique, passes, runKind, runSummary,
  shortModel, stepLabel, type TraceEvent,
} from "./parse.ts";

const ev = (over: Partial<TraceEvent>): TraceEvent => ({
  ts: "2026-10-26T14:05:24+00:00", run_id: "r", agent: "harness", kind: "decision",
  summary_in: "x", summary_out: "y", ok: true, model: null, latency_ms: null, ...over,
});

test("reads the draft out of the approval prompt", () => {
  const text = "Line one.\nLine two with --- dashes.";
  const prompt = `\n--- draft (${text.length} chars) ---\n${text}\n--- end ---\nPublish this post? [y/N] `;
  assert.deepEqual(parseApprovalPrompt(prompt), { text, chars: text.length });
  assert.equal(parseApprovalPrompt("Publish this post? [y/N] "), null);
});

test("parses a fenced critic answer with reasons", () => {
  const out = 'tokens in=1263 out=186 finish=stop: ```json\n{"voice": 5, "clarity": 4, "cta": 5, "policy_risk": 5, "reasons": {"clarity": "one idea"}}\n```';
  const c = parseCritique(out);
  assert.deepEqual(c?.scores, { voice: 5, clarity: 4, cta: 5, policy_risk: 5 });
  assert.equal(c?.reasons.clarity, "one idea");
});

test("still reads the scores when the trace truncated the middle of the JSON", () => {
  const out = 'tokens: {"voice": 4, "clarity": 3, "cta": 5, "policy_risk"...[truncated 900 chars]...: 5, "reasons": {"voice": "ok"}}';
  assert.equal(parseCritique(out), null, "policy_risk value was cut, so no partial scores are invented");
  const out2 = 'tokens: {"voice": 4, "clarity": 3, "cta": 5, "policy_risk": 5, "reasons": {"voice": "o...[truncated 9 chars]...k"}';
  assert.deepEqual(parseCritique(out2)?.scores, { voice: 4, clarity: 3, cta: 5, policy_risk: 5 });
});

test("one weak score fails, like the harness threshold", () => {
  assert.equal(passes({ voice: 5, clarity: 4, cta: 5, policy_risk: 5 }), true);
  assert.equal(passes({ voice: 5, clarity: 3, cta: 5, policy_risk: 5 }), false);
});

test("takes the last successful critic call and the latest pre-approval guardrails", () => {
  const events = [
    ev({ agent: "critic", kind: "llm_call", ok: true, summary_out: '{"voice":2,"clarity":2,"cta":2,"policy_risk":2,"reasons":{}}' }),
    ev({ kind: "guardrail", summary_in: "check_length | old", ok: false, summary_out: "too long" }),
    ev({ agent: "critic", kind: "llm_call", ok: true, summary_out: '{"voice":5,"clarity":4,"cta":5,"policy_risk":5,"reasons":{}}' }),
    ev({ agent: "critic", kind: "llm_call", ok: false, summary_out: "attempt failed: HTTP 429" }),
    ev({ kind: "guardrail", summary_in: "check_length | Feeding", summary_out: "pass" }),
    ev({ kind: "guardrail", summary_in: "check_banned | Feeding", summary_out: "pass" }),
    ev({ kind: "guardrail", summary_in: "publish re-check check_length | Feeding", summary_out: "pass" }),
  ];
  assert.equal(latestCritique(events)?.scores.clarity, 4);
  assert.deepEqual(latestGuardrails(events).map((g) => [g.name, g.ok]), [["length", true], ["banned", true]]);
});

test("counts llm_call events since a time, failed ones included", () => {
  const events = [
    ev({ kind: "llm_call", ts: "2026-10-26T10:00:00+00:00", ok: false }),
    ev({ kind: "llm_call", ts: "2026-10-26T14:00:00+00:00" }),
    ev({ kind: "decision", ts: "2026-10-26T14:00:00+00:00" }),
  ];
  assert.equal(countLlmCalls(events, new Date("2026-10-26T09:00:00Z")), 2);
  assert.equal(countLlmCalls(events, new Date("2026-10-26T12:00:00Z")), 1);
});

test("reads the run summary and the kind of run", () => {
  const events = [
    ev({ summary_in: "run_outer", summary_out: "start: dry_run=False approval=True measure_only=True min_score=4" }),
    ev({ summary_in: "run_summary sha256=abc", summary_out: '{"schema_version": 1, "exit_code": 0, "dry_run": false}' }),
  ];
  assert.equal(runSummary(events)?.exit_code, 0);
  assert.equal(runKind(events), "measure");
  assert.equal(runSummary([ev({})]), null);
});

test("labels steps compactly", () => {
  assert.equal(shortModel("google/gemma-4-31b-it:free"), "gemma-4-31b-it");
  assert.equal(stepLabel(ev({ agent: "critic", kind: "llm_call", ok: false, model: "google/gemma-4-31b-it:free", summary_out: "attempt 1/3 failed: HTTP 429: {}" })), "critic · gemma-4-31b-it · HTTP 429");
  assert.equal(stepLabel(ev({ kind: "guardrail", summary_in: "check_rate_cap | text", summary_out: "pass" })), "check_rate_cap → pass");
});

test("rate cap counts live and unsettled pending posts, never dry runs", async () => {
  const { rateCap } = await import("./parse.ts");
  const now = new Date("2026-10-28T12:00:00Z");
  const iso = (minAgo: number) => new Date(now.getTime() - minAgo * 60_000).toISOString();
  assert.equal(rateCap([], now).open, true);
  assert.equal(rateCap([{ run_id: "a", post_id: "p", status: "published", posted_at: iso(30) }], now).open, false);
  assert.equal(rateCap([{ run_id: "a", post_id: "p", status: "published", posted_at: iso(90) }], now).open, true);
  assert.equal(rateCap([{ run_id: "a", post_id: "p", posted_at: iso(30), dry_run: true }], now).open, true);
  const pendingOnly = rateCap([{ run_id: "a", post_id: "p", status: "pending", started_at: iso(10) }], now);
  assert.equal(pendingOnly.open, false, "a pending post with no outcome may be live");
  const failed = rateCap([{ run_id: "a", post_id: "p", status: "pending", started_at: iso(10) }, { run_id: "a", post_id: "p", status: "failed" }], now);
  assert.equal(failed.open, true, "an explicit failed row means nothing was sent");
  const three = [200, 400, 600].map((m, i) => ({ run_id: `r${i}`, post_id: "p", status: "published", posted_at: iso(m) }));
  const capped = rateCap(three, now);
  assert.equal(capped.open, false);
  assert.equal(capped.inWindow, 3);
});
