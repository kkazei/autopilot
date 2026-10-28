import { NextResponse } from "next/server";

import { backend } from "@/lib/backend";
import { latestRun } from "@/lib/db";
import { guard } from "@/lib/guard";
import { latestCritique, latestGuardrails, runSummary } from "@/lib/parse";

export const dynamic = "force-dynamic";

export type BackendStatus = {
  running: boolean; what: string; dry_run: boolean; log: string;
  approval: { id: number; prompt: string; dry_run: boolean } | null; exit_code: number | null;
};
export type Live = {
  backend: "up" | "down";
  status: BackendStatus | null;
  run: { run_id: string; updated_at: string; events: import("@/lib/parse").TraceEvent[]; finished: boolean;
         critique: ReturnType<typeof latestCritique>; guardrails: ReturnType<typeof latestGuardrails> } | null;
};

/** One poll for the control page: what the backend is doing, plus the trace it is writing (pushed live to Postgres). */
export async function GET(req: Request) {
  const denied = await guard(req);
  if (denied) return denied;
  const [status, run] = await Promise.all([
    backend("/status", {}, 8_000).then(async (r) => (r.ok ? ((await r.json()) as BackendStatus) : null)).catch(() => null),
    latestRun(),
  ]);
  const body: Live = {
    backend: status ? "up" : "down",
    status,
    run: run && {
      run_id: run.run_id, updated_at: run.updated_at, events: run.events.slice(-40), finished: runSummary(run.events) !== null,
      critique: latestCritique(run.events), guardrails: latestGuardrails(run.events),
    },
  };
  return NextResponse.json(body, { headers: { "cache-control": "no-store" } });
}
