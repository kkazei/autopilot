import assert from "node:assert/strict";
import { test } from "node:test";

import {
  countLlmCalls, describeEvents, describeRun, latestCritique, latestGuardrails, parseApprovalPrompt, parseCritique, passes, runKind, runSummary,
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

test("the live signature changes exactly when server data can be stale", async () => {
  const { liveSignature } = await import("./parse.ts");
  const base = { status: { running: true, approval: null }, run: { run_id: "r1", finished: false } };
  const same = liveSignature(base);
  assert.equal(liveSignature({ ...base }), same, "a plain poll with nothing new does not refresh");
  assert.notEqual(liveSignature({ ...base, status: { running: true, approval: { id: 1 } } }), same);
  assert.notEqual(liveSignature({ status: { running: false, approval: null }, run: { run_id: "r1", finished: true } }), same);
  assert.notEqual(liveSignature({ ...base, run: { run_id: "r2", finished: false } }), same);
  assert.equal(liveSignature(null), "");
});

test("the live request count adds only calls made after the page's own count", async () => {
  const { liveRequestCount } = await import("./parse.ts");
  const events = [
    ev({ kind: "llm_call", ts: "2026-10-28T14:00:55Z", ok: false }),
    ev({ kind: "llm_call", ts: "2026-10-28T14:01:04Z" }),
    ev({ kind: "decision", ts: "2026-10-28T14:01:05Z" }),
    ev({ kind: "llm_call", ts: "2026-10-28T14:01:09Z" }),
  ];
  assert.equal(liveRequestCount(4, "2026-10-28T14:01:00Z", events), 6, "the 14:00:55 call was already in the server's count");
  assert.equal(liveRequestCount(4, "2026-10-28T14:02:00Z", events), 4);
  assert.equal(liveRequestCount(0, "2026-10-28T13:00:00Z", events), 3, "failed attempts count too, like quota.py");
});

// Shapes copied from real run summaries (Neon, Oct 27 to 29).
const summary = (over: object) => ({ exit_code: 0, dry_run: false, outcomes: [], learnings: { saved: [], skipped: [] }, ...over });
const topics = (id: string) => ({ post_6b0ad6ec: "bake result" } as Record<string, string>)[id];

test("describes a run by what happened, not by its exit code", () => {
  const measure = (saved: string[]) => describeRun({ kind: "measure", summary: summary({ outcomes: [{ post_id: null, status: "skipped", reason: "measure only" }], learnings: { saved } }) });
  assert.deepEqual(measure(["post_6b0ad6ec"]), { title: "Measured", detail: "1 new learning saved", tone: "ok" });
  assert.equal(measure([]).detail, "nothing new to learn yet");

  const posted = describeRun({ kind: "post", summary: summary({ outcomes: [{ post_id: "post_6b0ad6ec", status: "published", reason: "published", uri: "at://did:plc:x/app.bsky.feed.post/3m" }] }) }, topics);
  assert.deepEqual(posted, { title: "Posted", detail: "“bake result” is on Bluesky", tone: "ok" });

  const dry = describeRun({ kind: "dry run", summary: summary({ dry_run: true, outcomes: [{ post_id: "post_6b0ad6ec", status: "published", reason: "published", uri: "dryrun://post_6b0ad6ec/05a8" }] }) });
  assert.equal(dry.title, "Dry run");
  assert.match(dry.detail, /nothing posted/);

  const refused = describeRun({ kind: "plan", summary: summary({ exit_code: 2, outcomes: [{ post_id: null, status: "skipped", reason: "refused: 3 posts are still waiting (next on 2026-10-28); plan now only runs when the queue is empty" }] }) });
  assert.deepEqual(refused, { title: "No plan", detail: "posts are still waiting in the queue", tone: "neutral" });

  const declined = describeRun({ kind: "post", summary: summary({ exit_code: 5, outcomes: [{ post_id: "post_d1104ff3", status: "blocked", reason: "blocked: require_approval: human reviewer did not approve" }] }) });
  assert.deepEqual(declined, { title: "Declined", detail: "you said no to the post", tone: "neutral" });

  assert.equal(describeRun({ kind: "post", summary: summary({ exit_code: 6 }) }).title, "Skipped");
  assert.equal(describeRun({ kind: "measure", summary: summary({ learnings: { saved: ["post_6b0ad6ec"] } }) }, topics).detail, "new learning from “bake result”");
  const deferred = describeRun({ kind: "post", summary: summary({ outcomes: [{ post_id: "post_6b0ad6ec", status: "carried_forward",
    reason: "no draft: LLMBudgetExceeded: critic: upstream attempt budget of 4 used" }] }) }, topics);
  assert.equal(deferred.detail, "it ran out of model requests; “bake result” waits for the next run");
  assert.equal(describeRun({ kind: "post", summary: summary({ outcomes: [{ post_id: null, status: "planned", reason: "planned 5 posts" }] }) }).detail, "queued 5 posts");
});

test("reads a topic post's outcome from its events, since run_post writes no summary", () => {
  const start = ev({ summary_in: "run_post", summary_out: "start: dry_run=False" });
  const blocked = ev({ summary_in: "publish post_857ad6bb", summary_out: "blocked: require_approval: human reviewer did not approve", ok: false });
  assert.equal(describeEvents([start, blocked]).title, "Declined");
  const failed = ev({ summary_in: "inner loop post_1b2578ab attempt 1", ok: false,
    summary_out: "failed: LLMOutputError: writer: invalid Draft after one repair attempt: text: is 391 characters; the limit is 300" });
  assert.deepEqual(describeEvents([start, failed]), { title: "Failed", detail: "the draft stayed at 391 characters (limit 300)", tone: "error" });
  const now = Date.parse("2026-10-26T14:10:00Z");
  assert.equal(describeEvents([start], undefined, now).title, "Running", "5 minutes since the last event");
  assert.equal(describeEvents([start], undefined, now + 60 * 60 * 1000).title, "Ended", "an hour of silence is not a live run");
});
