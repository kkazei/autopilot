import Link from "next/link";

import { Badge, Card, Empty, PageHeader } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { recentRuns } from "@/lib/db";
import { Time } from "@/components/time";
import { ago } from "@/lib/format";
import { EXIT_MEANINGS, exitTone, runKind, type RunSummary } from "@/lib/parse";

export const dynamic = "force-dynamic";

export default async function Runs() {
  await requireOwner();
  const runs = await recentRuns(60);
  return (
    <>
      <PageHeader title="Traces" sub="Every run, step by step: model calls, tool calls, guardrails and decisions. Open one to see its timeline." />
      <Card flush>
        {runs.length === 0 ? <Empty>No runs yet.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left">
              <thead className="bg-raised">
                <tr className="t-label text-fg-3">
                  {["run", "started", "kind", "events", "requests", "result"].map((h) => <th key={h} className="px-5 py-2 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {runs.map((r, idx) => {
                  const s = r.summary ? (JSON.parse(r.summary.summary_out) as RunSummary) : null;
                  return (
                    <tr key={r.run_id} className="animate-rise border-t border-line transition-colors hover:bg-raised/50" style={{ animationDelay: `${Math.min(idx, 24) * 22}ms` }}>
                      <td className="px-5 py-3"><Link href={`/runs/${r.run_id}`} className="t-mono-sm text-fg hover:underline">{r.run_id}</Link></td>
                      <td className="t-small px-5 py-3 text-fg-2"><Time iso={r.started_at} kind="stamp" /> <span className="text-fg-3">· {ago(r.started_at)}</span></td>
                      <td className="t-mono-sm px-5 py-3 text-fg-2">{r.first ? runKind([r.first]) : "—"}</td>
                      <td className="t-mono-sm px-5 py-3 text-fg-3">{r.n}</td>
                      <td className="t-mono-sm px-5 py-3 text-fg-3">{s?.requests ? `${s.requests.used}/${s.requests.limit}` : "—"}</td>
                      <td className="px-5 py-3"><Badge tone={exitTone(s?.exit_code)}>{s ? EXIT_MEANINGS[s.exit_code] ?? `exit ${s.exit_code}` : "running"}</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
