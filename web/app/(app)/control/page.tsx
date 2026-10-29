import Link from "next/link";

import { ApprovalCard, LatestRun, MeasureButton, RunButtons, TopicForm } from "@/components/control";
import { LiveQuota } from "@/components/live-quota";
import { CountUp, Reveal } from "@/components/motion";
import { Time } from "@/components/time";
import { Badge, Card, Dot, Empty, PageHeader, Stat } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { log, planState, recentRuns, requestsLast24h, type Learning } from "@/lib/db";
import { ago, until } from "@/lib/format";
import { rateCap, type ApprovedRow, type Tone } from "@/lib/parse";
import { rowStory, topicLookup } from "@/lib/runs";
import { dateLabel } from "@/lib/time";

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
  const topic = topicLookup(state.posts);
  const lastRun = runs[0];
  const last = lastRun ? rowStory(lastRun, topic, now.getTime()) : null;
  const learning = learnings.at(-1);
  const learningTopic = learning && state.posts.find((p) => p.id === learning.post_id)?.topic;


  return (
    <>
      <PageHeader title="Control"
        sub={<><Time iso={now.toISOString()} kind="day" /> · {plan ? `week of ${plan.week_of}` : "no plan yet"} · {waiting.length} post{waiting.length === 1 ? "" : "s"} waiting</>}>
        <RunButtons />
      </PageHeader>

      <Reveal className="grid auto-rows-fr grid-cols-2 gap-3 md:gap-4 xl:grid-cols-4">
        <LiveQuota base={used} baseAt={now.toISOString()} />
        <Stat label="next post" value={next ? dateLabel(next.day) : "—"} sub={next ? `${next.topic} · ${next.goal}` : "queue empty: plan next week"} />
        <Stat label="rate cap" value={cap.open ? "open" : "closed"}
          sub={cap.open ? <><CountUp value={cap.inWindow} />/3 in 24h · {cap.last ? `last post ${ago(cap.last.toISOString())}` : "no posts yet"}</> : `opens ${cap.opensAt ? until(cap.opensAt.toISOString(), now.getTime()) : "soon"}`} />
        <Stat label="last run" words href={lastRun ? `/runs/${lastRun.run_id}` : undefined}
          value={last ? <span className="flex items-center gap-2.5"><Dot tone={last.tone} className="size-2.5" />{last.title}</span> : "—"}
          sub={last && lastRun ? `${last.detail} · ${ago(lastRun.updated_at)}` : "no runs yet"} />
      </Reveal>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Reveal className="flex min-w-0 flex-col gap-6" step={0.07}>
          <ApprovalCard />
          <TopicForm />
          <Card flush title="This week" right={plan ? `${plan.plan_id} · ${week.length} posts` : undefined}>
            {week.length === 0 ? <Empty>No plan yet. “Plan next week” makes one.</Empty> : (
              <ul>
                {week.map((p) => (
                  <li key={p.id} className="flex items-center gap-3 border-t border-line px-5 py-3 transition-colors hover:bg-raised/40 md:gap-4">
                    <span className="t-mono-sm w-14 shrink-0 text-fg-3">{dateLabel(p.day)}</span>
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
        </Reveal>
        <Reveal className="flex min-w-0 flex-col gap-6" step={0.07}>
          <LatestRun />
          <Card title="Recent traces" right={<Link href="/runs" className="hover:text-fg">all →</Link>}>
            <ul className="-mx-2 flex flex-col">
              {runs.map((r) => {
                const story = rowStory(r, topic, now.getTime());
                return (
                  <li key={r.run_id}>
                    <Link href={`/runs/${r.run_id}`} className="flex items-start gap-3 rounded-md px-2 py-2 transition-colors hover:bg-raised">
                      <Dot tone={story.tone} className="mt-2" />
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="text-sm font-medium">{story.title}</span>
                        <span className="t-small truncate text-fg-3">{story.detail}</span>
                      </span>
                      <span className="t-small shrink-0 pt-0.5 text-fg-3">{ago(r.started_at)}</span>
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
            ) : <p className="t-small text-fg-3">Learnings appear after a measure run reads engagement.</p>}
            <div className="mt-4 flex items-center gap-3 border-t border-line pt-4">
              <Link href="/learnings" className="t-small text-fg-2 hover:text-fg">all learnings →</Link>
              <span className="ml-auto"><MeasureButton kind="ghost" /></span>
            </div>
          </Card>
        </Reveal>
      </div>
    </>
  );
}
