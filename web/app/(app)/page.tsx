import Link from "next/link";

import { ApprovalCard, LiveRun, RunButtons } from "@/components/control";
import { Badge, Card, Empty, Meter, PageHeader, Stat } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { log, planState, recentRuns, requestsLast24h, type Learning } from "@/lib/db";
import { ago, shortRun, until, utcDay } from "@/lib/format";
import { DAILY_REQUEST_LIMIT, EXIT_MEANINGS, exitTone, rateCap, type ApprovedRow, type RunSummary, type Tone } from "@/lib/parse";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, Tone> = { published: "ok", blocked: "error", failed: "error", escalated: "warn", planned: "neutral", carried_forward: "info" };

export default async function Control() {
  await requireOwner();
  const now = new Date();
  const [state, approved, learnings, runs, used] = await Promise.all([
    planState(), log<ApprovedRow>("approved.jsonl"), log<Learning>("learnings.jsonl"), recentRuns(5), requestsLast24h(),
  ]);
  const plan = state.plans.at(-1);
  const week = plan ? state.posts.filter((p) => p.plan_id === plan.plan_id) : [];
  const waiting = state.posts.filter((p) => p.status === "planned" || p.status === "carried_forward").sort((a, b) => a.day.localeCompare(b.day));
  const next = waiting[0];
  const cap = rateCap(approved, now);
  const lastRun = runs[0];
  const lastSummary = lastRun?.summary ? (JSON.parse(lastRun.summary.summary_out) as RunSummary) : null;
  const learning = learnings.at(-1);
  const learningTopic = learning && state.posts.find((p) => p.id === learning.post_id)?.topic;
  const left = DAILY_REQUEST_LIMIT - used;

  return (
    <>
      <PageHeader title="Control" sub={`${utcDay(now.toISOString())} · ${plan ? `week of ${plan.week_of}` : "no plan yet"} · ${waiting.length} post${waiting.length === 1 ? "" : "s"} waiting`}>
        <RunButtons />
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 md:gap-4 xl:grid-cols-4">
        <Stat label="model requests · 24h" value={`${used}/${DAILY_REQUEST_LIMIT}`} sub={left > 0 ? `${left} left · a run uses up to 16` : "daily cap reached"}>
          <Meter used={used} max={DAILY_REQUEST_LIMIT} />
        </Stat>
        <Stat label="next post" value={next ? utcDay(next.day) : "—"} sub={next ? `${next.topic} · ${next.goal}` : "queue empty: plan next week"} />
        <Stat label="rate cap" value={cap.open ? "open" : "closed"} sub={cap.open ? `${cap.inWindow}/3 in 24h · ${cap.last ? `last post ${ago(cap.last.toISOString())}` : "no posts yet"}` : `opens ${cap.opensAt ? until(cap.opensAt.toISOString(), now.getTime()) : "soon"}`} />
        <Stat label="last run" value={lastSummary ? `exit ${lastSummary.exit_code}` : "—"} sub={lastRun ? `${EXIT_MEANINGS[lastSummary?.exit_code ?? -1] ?? "running"} · ${ago(lastRun.updated_at)}` : "no runs yet"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_352px]">
        <div className="flex min-w-0 flex-col gap-6">
          <ApprovalCard />
          <Card flush title="This week" right={plan ? `${plan.plan_id} · ${week.length} posts` : undefined}>
            {week.length === 0 ? <Empty>No plan yet. “Plan next week” makes one.</Empty> : (
              <ul>
                {week.map((p) => (
                  <li key={p.id} className="flex items-center gap-3 border-t border-line px-5 py-3 md:gap-4">
                    <span className="t-mono-sm w-14 shrink-0 text-fg-3">{utcDay(p.day)}</span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm font-medium">{p.topic}</span>
                      <span className="t-small hidden truncate text-fg-2 sm:block">{p.angle}</span>
                    </span>
                    <span className="t-mono-sm hidden w-24 text-fg-2 md:block">{p.goal}</span>
                    <span className="flex w-28 justify-end"><Badge tone={STATUS_TONE[p.status] ?? "neutral"}>{p.status.replace("_", " ")}</Badge></span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          <LiveRun />
          <Card title="Recent runs" right={<Link href="/runs" className="hover:text-fg">all →</Link>}>
            <ul className="flex flex-col gap-3">
              {runs.map((r) => {
                const s = r.summary ? (JSON.parse(r.summary.summary_out) as RunSummary) : null;
                return (
                  <li key={r.run_id}>
                    <Link href={`/runs/${r.run_id}`} className="flex items-center gap-3 hover:opacity-80">
                      <span className="t-mono-sm text-fg-2">{shortRun(r.run_id)}</span>
                      <span className="t-small truncate text-fg-3">{ago(r.started_at)}</span>
                      <span className="ml-auto"><Badge tone={exitTone(s?.exit_code)}>{s ? EXIT_MEANINGS[s.exit_code] ?? `exit ${s.exit_code}` : "running"}</Badge></span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </Card>
          <Card title="Latest learning" right={learningTopic ?? learning?.post_id}>
            {learning ? (
              <div className="flex flex-col gap-3">
                <p>{learning.insight}</p>
                <p className="t-mono-sm flex gap-4 text-fg-2">
                  {Object.entries(learning.metrics).map(([k, v]) => <span key={k}>{v} {k}</span>)}
                </p>
              </div>
            ) : <p className="t-small text-fg-3">Learnings appear after the daily measure run reads engagement.</p>}
          </Card>
        </div>
      </div>
    </>
  );
}
