// Pure readers for what the harness writes. No I/O here, so every rule is unit tested (parse.test.ts).
// The formats come from the Python side: guardrails.require_approval's prompt, trace.TraceEvent, outer._log_summary.

export type TraceEvent = {
  ts: string;
  run_id: string;
  agent: "planner" | "writer" | "critic" | "analyst" | "harness";
  kind: "llm_call" | "tool_call" | "guardrail" | "decision";
  summary_in: string;
  summary_out: string;
  ok: boolean;
  model: string | null;
  latency_ms: number | null;
};

export type Scores = { voice: number; clarity: number; cta: number; policy_risk: number };
export type Critique = { scores: Scores; reasons: Partial<Record<keyof Scores, string>> };
export type Tone = "ok" | "warn" | "error" | "info" | "neutral";

export const SCORE_KEYS = ["voice", "clarity", "cta", "policy_risk"] as const;
export const PASS_SCORE = 4; // harness default --min-score
export const DAILY_REQUEST_LIMIT = 45; // harness/quota.py
export const MAX_POST_CHARS = 300; // harness/schemas.py

export const EXIT_MEANINGS: Record<number, string> = {
  0: "done", 2: "refused", 3: "escalated", 4: "failed", 5: "blocked", 6: "busy", 7: "not saved",
};

const PROMPT_RE = /--- draft \((\d+) chars\) ---\n([\s\S]*?)\n--- end ---/;

/** The draft the backend is waiting on, from guardrails.require_approval's prompt. */
export function parseApprovalPrompt(prompt: string): { text: string; chars: number } | null {
  const m = PROMPT_RE.exec(prompt);
  return m ? { text: m[2], chars: Number(m[1]) } : null;
}

/** Critic output as traced: "tokens ...: {json}", maybe fenced, maybe cut in the middle by the trace's head/tail truncation. */
export function parseCritique(summaryOut: string): Critique | null {
  const start = summaryOut.indexOf("{");
  const end = summaryOut.lastIndexOf("}");
  if (start >= 0 && end > start) {
    try {
      const obj = JSON.parse(summaryOut.slice(start, end + 1));
      const scores = pickScores(obj);
      if (scores) return { scores, reasons: typeof obj.reasons === "object" && obj.reasons ? obj.reasons : {} };
    } catch {
      // truncated: fall back to reading the numbers one by one
    }
  }
  const scores: Partial<Scores> = {};
  for (const k of SCORE_KEYS) {
    const m = new RegExp(`"${k}"\\s*:\\s*(\\d)`).exec(summaryOut);
    if (m) scores[k] = Number(m[1]);
  }
  return isScores(scores) ? { scores, reasons: {} } : null;
}

function pickScores(obj: unknown): Scores | null {
  if (!obj || typeof obj !== "object") return null;
  const o = obj as Record<string, unknown>;
  const s = Object.fromEntries(SCORE_KEYS.map((k) => [k, o[k]]));
  return isScores(s) ? s : null;
}

function isScores(s: Partial<Record<string, unknown>>): s is Scores {
  return SCORE_KEYS.every((k) => Number.isInteger(s[k]) && (s[k] as number) >= 1 && (s[k] as number) <= 5);
}

/** Mirrors schemas.passes_threshold: one weak score fails the draft. */
export function passes(scores: Scores, min = PASS_SCORE): boolean {
  return SCORE_KEYS.every((k) => scores[k] >= min);
}

/** The latest critique in a run: the last successful critic llm_call that parses. */
export function latestCritique(events: TraceEvent[]): Critique | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.agent === "critic" && e.kind === "llm_call" && e.ok) {
      const c = parseCritique(e.summary_out);
      if (c) return c;
    }
  }
  return null;
}

const GUARDS = ["check_length", "check_banned", "check_rate_cap", "check_duplicate"] as const;

/** The pre-approval guardrail results of the latest attempt (not the publish re-check). */
export function latestGuardrails(events: TraceEvent[]): { name: string; ok: boolean; detail: string }[] {
  const found = new Map<string, { name: string; ok: boolean; detail: string }>();
  for (let i = events.length - 1; i >= 0 && found.size < GUARDS.length; i--) {
    const e = events[i];
    if (e.kind !== "guardrail") continue;
    const name = e.summary_in.split(" | ")[0];
    if ((GUARDS as readonly string[]).includes(name) && !found.has(name)) {
      found.set(name, { name: name.replace("check_", "").replace("_", " "), ok: e.ok, detail: e.summary_out });
    }
  }
  return GUARDS.filter((g) => found.has(g)).map((g) => found.get(g)!);
}

/** Same rule as quota.llm_calls_since: every llm_call event, failed attempts included. */
export function countLlmCalls(events: TraceEvent[], since: Date): number {
  return events.filter((e) => e.kind === "llm_call" && new Date(e.ts) >= since).length;
}

export type RunSummary = {
  exit_code: number;
  dry_run: boolean;
  requests?: { used: number; limit: number };
  outcomes?: { post_id: string | null; status: string; reason: string; uri?: string }[];
};

/** The run_summary event is written untruncated as JSON (outer._log_summary). Absent while the run is going. */
export function runSummary(events: TraceEvent[]): RunSummary | null {
  const e = [...events].reverse().find((x) => x.summary_in.startsWith("run_summary"));
  if (!e) return null;
  try {
    return JSON.parse(e.summary_out) as RunSummary;
  } catch {
    return null;
  }
}

/** What kind of run this was, from its first event ("start: dry_run=... measure_only=..." or plan_now). */
export function runKind(events: TraceEvent[]): string {
  const first = events[0];
  if (!first) return "run";
  if (first.summary_in === "plan_now") return "plan";
  if (first.summary_out.includes("measure_only=True")) return "measure";
  if (first.summary_in.startsWith("run_post")) return "topic post";
  return first.summary_out.includes("dry_run=True") ? "dry run" : "post";
}

export function exitTone(code: number | null | undefined): Tone {
  if (code === null || code === undefined) return "info";
  if (code === 0) return "ok";
  if (code === 3 || code === 6) return "warn";
  if (code === 2) return "neutral";
  return "error";
}

/** "google/gemma-4-31b-it:free" -> "gemma-4-31b-it" */
export function shortModel(model: string | null): string {
  if (!model) return "";
  return model.split("/").pop()!.replace(/:free$/, "");
}

/** One readable line per event for the live run panel. */
export function stepLabel(e: TraceEvent): string {
  const head = e.summary_in.split(" | ")[0];
  if (e.kind === "llm_call") {
    const failed = e.ok ? "" : ` · ${e.summary_out.match(/HTTP \d{3}/)?.[0] ?? "failed"}`;
    return `${e.agent} · ${shortModel(e.model)}${failed}`;
  }
  if (e.kind === "guardrail") return `${head} → ${e.summary_out}`;
  if (e.kind === "tool_call") return `${head} → ${e.ok ? "ok" : "failed"}`;
  if (head.startsWith("run_summary")) return "run finished";
  return `${head}: ${e.summary_out}`;
}

export function eventTone(e: TraceEvent): Tone {
  return e.ok ? "ok" : "error";
}

/** Seconds between the first and last event; null for an empty trace. */
export function durationSeconds(events: TraceEvent[]): number | null {
  if (events.length === 0) return null;
  return Math.max(0, Math.round((Date.parse(events[events.length - 1].ts) - Date.parse(events[0].ts)) / 1000));
}

export type ApprovedRow = { run_id?: string; post_id?: string; status?: string; posted_at?: string; started_at?: string; dry_run?: boolean };

/** publish.live_records + guardrails.check_rate_cap: max 3 posts per 24h and 60 minutes between posts.
 * A pending row with no outcome still counts (the post may be live); only a "failed" row settles it as not sent. */
export function rateCap(rows: ApprovedRow[], now: Date, maxPerDay = 3, minGapMin = 60) {
  const pending = new Map<string, string | undefined>();
  const settled = new Set<string>();
  const times: number[] = [];
  for (const r of rows) {
    if (r.dry_run) continue;
    const key = `${r.run_id}/${r.post_id}`;
    const status = r.status ?? "published";
    if (status === "pending") pending.set(key, r.started_at);
    else {
      settled.add(key);
      if (status !== "failed" && r.posted_at) times.push(Date.parse(r.posted_at));
    }
  }
  for (const [key, at] of pending) if (!settled.has(key) && at) times.push(Date.parse(at));
  const dayAgo = now.getTime() - 24 * 3600_000;
  const inWindow = times.filter((t) => t > dayAgo).sort((a, b) => a - b);
  const last = times.length ? Math.max(...times) : null;
  const gapOpensAt = last === null ? 0 : last + minGapMin * 60_000;
  const windowOpensAt = inWindow.length >= maxPerDay ? inWindow[inWindow.length - maxPerDay] + 24 * 3600_000 : 0;
  const opensAt = Math.max(gapOpensAt, windowOpensAt);
  return { open: opensAt <= now.getTime(), opensAt: opensAt > now.getTime() ? new Date(opensAt) : null, inWindow: inWindow.length, last: last === null ? null : new Date(last) };
}
