import { neon } from "@neondatabase/serverless";

import type { TraceEvent } from "./parse";

// Read-only views over the tables harness/db_store.py creates. Writes happen only in the Python backend.
function sql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  return neon(url);
}

export type PostRecord = {
  id: string; plan_id: string; day: string; topic: string; angle: string; goal: string; status: string;
  runs_failed: number; uri: string | null; history: { run_id: string; status: string; at: string; reason: string }[];
};
export type PlanRecord = { plan_id: string; run_id: string; week_of: string; rationale: string; created_at: string };
export type PlanState = { plans: PlanRecord[]; posts: PostRecord[] };
export type Approved = { run_id?: string; post_id?: string; status?: string; text?: string; uri?: string; posted_at?: string; dry_run?: boolean };
export type Learning = { run_id: string; post_id: string; metrics: Record<string, number>; insight: string };
export type RunRow = {
  run_id: string; started_at: string; updated_at: string; n: number;
  first: TraceEvent | null; summary: TraceEvent | null; publish: TraceEvent | null; last: TraceEvent | null;
};

export async function planState(): Promise<PlanState> {
  const rows = await sql()`select data from docs where name = 'plan_state.json'`;
  const data = rows[0]?.data as Partial<PlanState> | undefined;
  return { plans: data?.plans ?? [], posts: data?.posts ?? [] };
}

export async function brandName(): Promise<string> {
  const rows = await sql()`select data->>'name' as name from docs where name = 'brand_brief.json'`;
  return (rows[0]?.name as string | undefined) ?? "Autopilot";
}

export async function log<T>(name: string): Promise<T[]> {
  const rows = await sql()`select data from log_records where log = ${name} order by seq`;
  return rows.map((r) => r.data as T);
}

export async function recentRuns(limit = 20): Promise<RunRow[]> {
  const rows = await sql()`
    select run_id, started_at, updated_at, jsonb_array_length(events) as n, events->0 as first, events->-1 as last,
           (select e from jsonb_array_elements(events) e where e->>'summary_in' like 'run_summary%' limit 1) as summary,
           (select e from jsonb_array_elements(events) e
             where e->>'kind' = 'decision' and e->>'summary_in' like 'publish post_%' limit 1) as publish
    from runs order by started_at desc limit ${limit}`;
  return rows as RunRow[];
}

export async function runEvents(runId: string): Promise<{ run_id: string; started_at: string; updated_at: string; events: TraceEvent[] } | null> {
  const rows = await sql()`select run_id, started_at, updated_at, events from runs where run_id = ${runId}`;
  return (rows[0] as { run_id: string; started_at: string; updated_at: string; events: TraceEvent[] }) ?? null;
}

/** The run most recently written to, which is the live one while a hosted run is going. */
export async function latestRun(): Promise<{ run_id: string; updated_at: string; events: TraceEvent[] } | null> {
  const rows = await sql()`select run_id, updated_at, events from runs order by updated_at desc limit 1`;
  return (rows[0] as { run_id: string; updated_at: string; events: TraceEvent[] }) ?? null;
}

/** quota.llm_calls_since over the last 24 hours, counted in the database. */
export async function requestsLast24h(): Promise<number> {
  const rows = await sql()`
    select count(*)::int as n from runs r, jsonb_array_elements(r.events) e
    where r.started_at > now() - interval '48 hours' and e->>'kind' = 'llm_call'
      and (e->>'ts')::timestamptz >= now() - interval '24 hours'`;
  return (rows[0]?.n as number) ?? 0;
}
