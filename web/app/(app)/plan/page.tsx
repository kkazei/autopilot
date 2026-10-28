import { RequeueButton } from "@/components/requeue";
import { Badge, Card, Empty, PageHeader } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { planState } from "@/lib/db";
import { Time } from "@/components/time";
import { dateLabel } from "@/lib/time";
import type { Tone } from "@/lib/parse";

export const dynamic = "force-dynamic";

const TONE: Record<string, Tone> = { published: "ok", blocked: "error", failed: "error", escalated: "warn", planned: "neutral", carried_forward: "info" };

export default async function Plan() {
  await requireOwner();
  const state = await planState();
  const plans = [...state.plans].reverse();
  return (
    <>
      <PageHeader title="Plan" sub="Each week's plan and what happened to every post. Escalated posts can go back in the queue." />
      {plans.length === 0 && <Card><p className="t-small text-fg-3">No plan yet. “Plan next week” on Control makes one.</p></Card>}
      {plans.map((plan) => {
        const posts = state.posts.filter((p) => p.plan_id === plan.plan_id);
        return (
          <Card key={plan.plan_id} flush title={`Week of ${plan.week_of}`} right={<>{plan.plan_id} · <Time iso={plan.created_at} kind="stamp" /></>}>
            <p className="t-small px-5 pb-4 text-fg-2">{plan.rationale}</p>
            {posts.length === 0 ? <Empty>No posts.</Empty> : (
              <ul>
                {posts.map((p) => (
                  <li key={p.id} className="border-t border-line px-5 py-3">
                    <details className="group">
                      <summary className="flex cursor-pointer list-none items-center gap-3 md:gap-4">
                        <span className="t-mono-sm w-14 shrink-0 text-fg-3">{dateLabel(p.day)}</span>
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="truncate text-sm font-medium">{p.topic}</span>
                          <span className="t-small truncate text-fg-2">{p.angle}</span>
                        </span>
                        <span className="t-mono-sm hidden w-24 text-fg-2 md:block">{p.goal}</span>
                        <Badge tone={TONE[p.status] ?? "neutral"}>{p.status.replace("_", " ")}</Badge>
                      </summary>
                      <div className="mt-3 flex flex-col gap-2 pl-0 md:pl-[4.5rem]">
                        <span className="t-mono-sm text-fg-3">{p.id}{p.uri ? ` · ${p.uri}` : ""}</span>
                        <ol className="flex flex-col gap-1">
                          {p.history.map((h, i) => (
                            <li key={i} className="t-mono-sm flex flex-wrap gap-x-3 text-fg-2">
                              <Time iso={h.at} kind="stamp" className="text-fg-3" /><span>{h.status}</span><span className="text-fg-3">{h.reason}</span>
                            </li>
                          ))}
                        </ol>
                        {p.status === "escalated" && <RequeueButton postId={p.id} />}
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        );
      })}
    </>
  );
}
