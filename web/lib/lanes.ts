import { shortModel, stepLabel, type TraceEvent } from "./parse.ts";

// Trace events as one lane per agent on a shared clock, for the run timeline (components/kokonutui/run-lanes.tsx).

export type StepTone = "model" | "model-failed" | "guard" | "guard-failed" | "wait" | "tool" | "decision" | "decision-failed";
export type LaneStep = { index: number; tone: StepTone; label: string; detail: string; start: number; end: number };
export type Lane = { id: string; name: string; steps: LaneStep[] };

const ORDER = ["planner", "writer", "critic", "analyst", "harness"] as const;

function tone(e: TraceEvent): StepTone {
  if (e.kind === "llm_call") return e.ok ? "model" : "model-failed";
  if (e.kind === "tool_call") return "tool";
  if (e.kind === "guardrail") return e.summary_in.startsWith("require_approval") ? "wait" : e.ok ? "guard" : "guard-failed";
  return e.ok ? "decision" : "decision-failed";
}

/** Seconds from the first event. Model calls span their latency (the event is written when the call returns); the
 * approval wait spans from the previous event to the answer; instant events get a small width and are nudged right so
 * a burst of them stays readable instead of stacking on one pixel. */
export function toLanes(events: TraceEvent[]): { lanes: Lane[]; total: number } {
  if (events.length === 0) return { lanes: [], total: 0 };
  const t0 = Math.min(...events.map((e) => Date.parse(e.ts) - (e.latency_ms ?? 0)));
  const at = (e: TraceEvent) => (Date.parse(e.ts) - t0) / 1000;
  const rawTotal = Math.max(...events.map(at), 1);
  const minWidth = Math.max(0.2, rawTotal * 0.012);
  const byAgent = new Map<string, LaneStep[]>();
  events.forEach((e, index) => {
    const end = at(e);
    let start = e.latency_ms ? end - e.latency_ms / 1000 : end;
    if (tone(e) === "wait" && index > 0) start = at(events[index - 1]);
    const steps = byAgent.get(e.agent) ?? [];
    const prevEnd = steps.at(-1)?.end ?? -Infinity;
    if (end - start < minWidth) start = Math.max(start, prevEnd);
    const width = Math.max(end - start, minWidth);
    const model = shortModel(e.model);
    steps.push({ index, tone: tone(e), label: stepLabel(e), detail: [model, e.latency_ms ? `${e.latency_ms} ms` : ""].filter(Boolean).join(" · "), start, end: start + width });
    byAgent.set(e.agent, steps);
  });
  const lanes = ORDER.filter((a) => byAgent.has(a)).map((a) => ({ id: a, name: a, steps: byAgent.get(a)! }));
  return { lanes, total: Math.max(...lanes.flatMap((l) => l.steps.map((s) => s.end))) };
}
