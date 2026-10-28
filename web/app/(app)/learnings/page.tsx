import { ArrowUpRight, Heart, Lightbulb, MessageCircle, Repeat2 } from "lucide-react";
import Link from "next/link";

import { FilterTabs } from "@/components/filter-tabs";
import { CountUp, Reveal } from "@/components/motion";
import { Time } from "@/components/time";
import { Badge, Card, PageHeader } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { log, planState } from "@/lib/db";
import { groupLearnings, type ApprovedPost, type LearningRow, type PostLearnings } from "@/lib/learnings";

export const dynamic = "force-dynamic";

const FILTERS = { all: "all", lessons: "has a lesson", waiting: "waiting for data" } as const;
type Filter = keyof typeof FILTERS;

export default async function Learnings({ searchParams }: { searchParams: Promise<{ f?: string }> }) {
  await requireOwner();
  const [{ f }, rows, approved, state] = await Promise.all([searchParams, log<LearningRow>("learnings.jsonl"), log<ApprovedPost>("approved.jsonl"), planState()]);
  const groups = groupLearnings(rows, approved, state.posts);
  const filter: Filter = f === "lessons" || f === "waiting" ? f : "all";
  const shown = groups.filter((g) => filter === "all" || (filter === "lessons" ? g.lesson : !g.lesson));
  const totals = groups.reduce((t, g) => {
    for (const k of ["likes", "reposts", "replies"] as const) t[k] += g.latest.metrics[k] ?? 0;
    return t;
  }, { likes: 0, reposts: 0, replies: 0 });
  const counts = { all: groups.length, lessons: groups.filter((g) => g.lesson).length, waiting: groups.filter((g) => !g.lesson).length };

  return (
    <>
      <PageHeader title="Learnings" sub="What each published post taught the planner. The latest lesson per post feeds next week's plan." />

      <Reveal className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <Summary label="posts measured" value={groups.length} />
        <Summary label="lessons for the planner" value={counts.lessons} />
        <Summary label="likes · latest reads" value={totals.likes} />
        <Summary label="reposts + replies" value={totals.reposts + totals.replies} />
      </Reveal>

      <FilterTabs id="learnings" options={(Object.keys(FILTERS) as Filter[]).map((k) => ({
        href: k === "all" ? "/learnings" : `/learnings?f=${k}`, label: FILTERS[k], count: counts[k], on: filter === k,
      }))} />

      {shown.length === 0 ? (
        <Card><p className="t-small text-fg-3">{groups.length === 0 ? "Learnings appear after the daily measure run reads engagement on posts older than 2 hours." : "Nothing in this filter."}</p></Card>
      ) : (
        <Reveal key={filter} className="flex flex-col gap-4" step={0.06}>
          {shown.map((g) => <PostCard key={g.post_id} g={g} />)}
        </Reveal>
      )}
    </>
  );
}

function Summary({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-line bg-surface p-4">
      <span className="t-label text-fg-3">{label}</span>
      <span className="t-metric"><CountUp value={value} /></span>
    </div>
  );
}

const METRICS = [["likes", Heart], ["reposts", Repeat2], ["replies", MessageCircle]] as const;

function PostCard({ g }: { g: PostLearnings }) {
  return (
    <article className="group flex flex-col gap-4 rounded-lg border border-line bg-surface p-4 transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-line-strong md:p-5">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {g.posted_at ? <Time iso={g.posted_at} kind="stamp" className="t-mono-sm text-fg-2" /> : <span className="t-mono-sm text-fg-3">not found in the post log</span>}
        {g.topic ? <Badge tone="info">{g.topic}</Badge> : <Badge tone="neutral">topic post</Badge>}
        {g.goal && <span className="t-mono-sm text-fg-3">{g.goal}</span>}
        <span className="t-mono-sm text-fg-3">{g.post_id}</span>
        {g.bluesky && (
          <a href={g.bluesky} target="_blank" rel="noreferrer" className="t-small ml-auto inline-flex items-center gap-1 text-fg-2 hover:text-fg">
            View on Bluesky <ArrowUpRight className="size-3.5" />
          </a>
        )}
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
        <blockquote className="rounded-md border border-line bg-inset px-4 py-3 text-[15px] leading-relaxed text-fg">
          {g.text ?? <span className="text-fg-3">The post text was not found.</span>}
        </blockquote>
        <dl className="grid grid-cols-3 gap-2 lg:w-72">
          {METRICS.map(([k, IconC]) => (
            <div key={k} className="flex flex-col items-start gap-1 rounded-md border border-line bg-raised px-3 py-2">
              <dt className="t-label flex items-center gap-1 text-fg-3"><IconC className="size-3" />{k}</dt>
              <dd className="t-metric"><CountUp value={g.latest.metrics[k] ?? 0} /></dd>
            </div>
          ))}
        </dl>
      </div>

      {g.lesson ? (
        <div className="flex gap-3 rounded-md border border-info/30 bg-info-bg px-4 py-3">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-info" />
          <div className="flex flex-col gap-1">
            <span className="t-label text-info">lesson for the planner</span>
            <p className="text-sm text-fg">{g.lesson.insight}</p>
          </div>
        </div>
      ) : (
        <p className="t-small rounded-md border border-dashed border-line px-4 py-3 text-fg-3">
          Waiting for data: fewer than 2 likes, reposts and replies so far, so no lesson yet. The daily measure run checks again.
        </p>
      )}

      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="t-label mr-1 text-fg-3">measured</span>
        {g.measurements.map((m, i) => (
          <li key={m.run_id} className="flex items-center gap-2">
            {i > 0 && <span className="text-fg-3" aria-hidden>→</span>}
            <Link href={`/runs/${m.run_id}`} className="t-mono-sm inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-fg-2 transition-colors hover:bg-raised hover:text-fg">
              {m.at ? <Time iso={m.at} kind="stamp" /> : m.run_id}
              <span className={m.thin ? "text-fg-3" : "text-ok"}>{m.thin ? "not enough data" : "lesson"}</span>
            </Link>
          </li>
        ))}
      </ol>
    </article>
  );
}
