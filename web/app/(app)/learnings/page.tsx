import Link from "next/link";

import { Card, PageHeader } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { log, planState, type Learning } from "@/lib/db";

export const dynamic = "force-dynamic";

const NOT_ENOUGH = "Not enough data yet"; // harness/measure.py NOT_ENOUGH_DATA_INSIGHT

export default async function Learnings() {
  await requireOwner();
  const [learnings, state] = await Promise.all([log<Learning>("learnings.jsonl"), planState()]);
  const topic = (id: string) => state.posts.find((p) => p.id === id)?.topic;
  return (
    <>
      <PageHeader title="Learnings" sub="What engagement taught the planner. Each one feeds the next week's plan." />
      {learnings.length === 0 && <Card><p className="t-small text-fg-3">Learnings appear after the daily measure run reads engagement on posts older than 2 hours.</p></Card>}
      <div className="grid gap-4 md:grid-cols-2">
        {[...learnings].reverse().map((l, i) => {
          const thin = l.insight.startsWith(NOT_ENOUGH);
          return (
            <Card key={i} title={topic(l.post_id) ?? l.post_id} right={<Link href={`/runs/${l.run_id}`} className="hover:text-fg">trace →</Link>}>
              <p className={thin ? "text-fg-3" : undefined}>{l.insight}</p>
              <p className="t-mono-sm mt-3 flex gap-4 text-fg-2">
                {Object.entries(l.metrics).map(([k, v]) => <span key={k}>{v} {k}</span>)}
              </p>
            </Card>
          );
        })}
      </div>
    </>
  );
}
