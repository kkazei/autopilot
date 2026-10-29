import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { Badge, Card, Empty, PageHeader } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { planState, recentRuns } from "@/lib/db";
import { Time } from "@/components/time";
import { ago } from "@/lib/format";
import { runKind, type RunSummary } from "@/lib/parse";
import { rowStory, topicLookup } from "@/lib/runs";

export const dynamic = "force-dynamic";

export default async function Runs() {
  await requireOwner();
  const [runs, state] = await Promise.all([recentRuns(60), planState()]);
  const topic = topicLookup(state.posts);
  const now = Date.now();
  return (
    <>
      <PageHeader title="Traces" sub="Every run, step by step: model calls, tool calls, guardrails and decisions. Open one to see its timeline." />
      <Card flush>
        {runs.length === 0 ? <Empty>No runs yet.</Empty> : (
          <>
          {/* Phones: one tappable row per run, what it was and when first; the id is secondary. */}
          <ul className="md:hidden">
            {runs.map((r, idx) => {
              const s = r.summary ? (JSON.parse(r.summary.summary_out) as RunSummary) : null;
              const story = rowStory(r, topic, now);
              return (
                <li key={r.run_id} className="animate-rise border-t border-line first:border-t-0" style={{ animationDelay: `${Math.min(idx, 24) * 22}ms` }}>
                  <Link href={`/runs/${r.run_id}`} className="flex items-center gap-3 px-4 py-3 transition-colors active:bg-raised">
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="flex items-baseline gap-2">
                        <span className="text-sm font-medium">{r.first ? runKind([r.first]) : "run"}</span>
                        <span className="t-small truncate text-fg-3"><Time iso={r.started_at} kind="stamp" /> · {ago(r.started_at)}</span>
                      </span>
                      <span className="t-small truncate text-fg-2">{story.detail}</span>
                      <span className="t-mono-sm truncate text-fg-3">
                        {r.n} events{s?.requests ? ` · ${s.requests.used}/${s.requests.limit} requests` : ""}
                      </span>
                    </span>
                    <Badge tone={story.tone}>{story.title}</Badge>
                    <ChevronRight className="size-4 shrink-0 text-fg-3" />
                  </Link>
                </li>
              );
            })}
          </ul>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[640px] text-left">
              <thead className="bg-raised">
                <tr className="t-label text-fg-3">
                  {["started", "kind", "what happened", "requests", "events", "run"].map((h) => <th key={h} className="px-5 py-2 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {runs.map((r, idx) => {
                  const s = r.summary ? (JSON.parse(r.summary.summary_out) as RunSummary) : null;
                  const story = rowStory(r, topic, now);
                  return (
                    <tr key={r.run_id} className="animate-rise border-t border-line transition-colors hover:bg-raised/50" style={{ animationDelay: `${Math.min(idx, 24) * 22}ms` }}>
                      <td className="t-small px-5 py-3 whitespace-nowrap text-fg-2"><Time iso={r.started_at} kind="stamp" /> <span className="text-fg-3">· {ago(r.started_at)}</span></td>
                      <td className="t-mono-sm px-5 py-3 whitespace-nowrap text-fg-2">{r.first ? runKind([r.first]) : "—"}</td>
                      <td className="px-5 py-3">
                        <Link href={`/runs/${r.run_id}`} className="group flex min-w-0 items-center gap-3">
                          <Badge tone={story.tone}>{story.title}</Badge>
                          <span className="t-small truncate text-fg-2 group-hover:text-fg">{story.detail}</span>
                        </Link>
                      </td>
                      <td className="t-mono-sm px-5 py-3 text-fg-3">{s?.requests ? `${s.requests.used}/${s.requests.limit}` : "—"}</td>
                      <td className="t-mono-sm px-5 py-3 text-fg-3">{r.n}</td>
                      <td className="px-5 py-3"><Link href={`/runs/${r.run_id}`} className="t-mono-sm whitespace-nowrap text-fg-3 hover:text-fg hover:underline">{r.run_id.slice(4)}</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          </>
        )}
      </Card>
    </>
  );
}
