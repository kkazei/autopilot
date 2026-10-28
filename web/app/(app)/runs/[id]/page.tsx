import Link from "next/link";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";

import { Reveal } from "@/components/motion";
import { Time } from "@/components/time";
import { TraceLanes } from "@/components/trace-lanes";
import { Badge, Card, cx, Dot, PageHeader, Stat } from "@/components/ui";
import { requireOwner } from "@/lib/auth";
import { runEvents } from "@/lib/db";
import { durationSeconds, EXIT_MEANINGS, exitTone, runKind, runSummary, shortModel, type TraceEvent } from "@/lib/parse";

export const dynamic = "force-dynamic";

const KINDS = [["all", "all"], ["llm", "llm_call"], ["tool", "tool_call"], ["guardrail", "guardrail"], ["decision", "decision"]] as const;
const RUN_ID = /^[A-Za-z0-9_-]{1,80}$/;

export default async function RunTrace({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ kind?: string; failed?: string; e?: string }> }) {
  await requireOwner();
  const [{ id }, q] = await Promise.all([params, searchParams]);
  if (!RUN_ID.test(id)) notFound();
  const run = await runEvents(id);
  if (!run) notFound();
  const events = run.events;
  const summary = runSummary(events);
  const kind = KINDS.find(([k]) => k === q.kind)?.[1] ?? "all";
  const failedOnly = q.failed === "1";
  const rows = events.map((e, i) => [e, i] as const).filter(([e]) => (kind === "all" || e.kind === kind) && (!failedOnly || !e.ok));
  const selected = q.e !== undefined && events[Number(q.e)] ? Number(q.e) : rows.find(([e]) => !e.ok)?.[1] ?? rows.at(-1)?.[1];
  const sel = selected !== undefined ? events[selected] : undefined;
  const llm = events.filter((e) => e.kind === "llm_call");
  const models = [...new Set(llm.map((e) => shortModel(e.model)).filter(Boolean))];
  const guards = events.filter((e) => e.kind === "guardrail");
  const href = (over: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    const merged = { kind: q.kind, failed: q.failed, e: q.e, ...over };
    for (const [k, v] of Object.entries(merged)) if (v) p.set(k, v);
    const s = p.toString();
    return `/runs/${id}${s ? `?${s}` : ""}`;
  };
  const dur = durationSeconds(events);

  return (
    <>
      <PageHeader crumb={<><Link href="/runs" className="hover:text-fg">Traces</Link>  /  {id}</>}
        title={<span className="flex flex-wrap items-center gap-3"><Time iso={run.started_at} kind="stamp" /> · {runKind(events)}
          <Badge tone={exitTone(summary?.exit_code)}>{summary ? EXIT_MEANINGS[summary.exit_code] ?? `exit ${summary.exit_code}` : "running"}</Badge>
          {summary?.dry_run && <Badge tone="info">dry run</Badge>}</span>} />

      <Reveal className="grid grid-cols-2 gap-3 md:gap-4 xl:grid-cols-5">
        <Stat label="duration" value={dur === null ? "—" : `${dur}s`} sub={summary ? "first to last event" : "still running"} />
        <Stat label="model requests" value={llm.length} sub={`${llm.filter((e) => !e.ok).length} failed (429s, timeouts)`} />
        <Stat label="models" value={models.length} sub={models.join(" → ") || "none"} />
        <Stat label="guardrails" value={`${guards.filter((e) => e.ok).length}/${guards.length}`} sub="pre-check and publish re-check" />
        <Stat label="events" value={events.length} sub="redacted before they are written" />
      </Reveal>

      <Card title="Timeline" right={<span className="hidden sm:inline">click a bar to open the event</span>}>
        <TraceLanes runId={id} events={events} selected={selected} live={!summary} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_352px]">
        <Card flush className="min-w-0 overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
            {KINDS.map(([label, k]) => {
              const n = k === "all" ? events.length : events.filter((e) => e.kind === k).length;
              const on = kind === k;
              return (
                <Link key={label} href={href({ kind: label === "all" ? undefined : label, e: undefined })}
                  className={cx("t-mono-sm inline-flex gap-2 rounded-md border px-3 py-1", on ? "border-line-strong bg-raised text-fg" : "border-line text-fg-2 hover:text-fg")}>
                  {label}<span className="text-fg-3">{n}</span>
                </Link>
              );
            })}
            <Link href={href({ failed: failedOnly ? undefined : "1", e: undefined })}
              className={cx("t-mono-sm ml-auto inline-flex items-center gap-2 rounded-md px-3 py-1", failedOnly ? "bg-err-bg text-err" : "text-fg-2 hover:text-fg")}>
              <Dot tone="error" />{events.filter((e) => !e.ok).length} failed
            </Link>
          </div>
          <div className="overflow-x-auto">
            <div className="min-w-[680px]">
              <div className="t-label grid grid-cols-[64px_8px_64px_80px_minmax(0,1fr)_150px_56px] gap-3 bg-raised px-3 py-2 text-fg-3">
                <span>time</span><span /><span>agent</span><span>kind</span><span>summary</span><span>model</span><span className="text-right">ms</span>
              </div>
              {rows.map(([e, i], n) => <TraceRow key={i} e={e} n={n} href={href({ e: String(i) })} selected={i === selected} />)}
              {rows.length === 0 && <p className="t-small px-5 py-4 text-fg-3">No events match.</p>}
            </div>
          </div>
        </Card>
        {sel && <EventDetail e={sel} />}
      </div>
    </>
  );
}

function summaryText(e: TraceEvent) {
  const head = e.summary_in.split(" | ")[0];
  if (e.kind === "llm_call") return e.summary_out.replace(/^tokens[^:]*:\s*/, "").replace(/\s+/g, " ");
  return `${head} → ${e.summary_out}`;
}

function TraceRow({ e, n, href, selected }: { e: TraceEvent; n: number; href: string; selected: boolean }) {
  return (
    <Link href={href} scroll={false} aria-current={selected ? "true" : undefined} style={{ animationDelay: `${Math.min(n, 24) * 22}ms` }}
      className={cx("animate-rise grid grid-cols-[64px_8px_64px_80px_minmax(0,1fr)_150px_56px] items-center gap-3 border-b border-line px-3 py-2 hover:bg-raised/60",
        selected && "border-l-2 border-l-info bg-raised")}>
      <Time iso={e.ts} kind="time" className="t-mono-sm text-fg-3" />
      <Dot tone={e.ok ? "ok" : "error"} className="size-2" />
      <span className="t-mono-sm text-fg-2">{e.agent}</span>
      <span className="t-mono-sm text-fg-3">{e.kind}</span>
      <span className={cx("truncate text-sm", e.ok ? "text-fg" : "text-err")}>{summaryText(e)}</span>
      <span className="t-mono-sm truncate text-fg-2">{shortModel(e.model) || "—"}</span>
      <span className="t-mono-sm text-right text-fg-3">{e.latency_ms ?? ""}</span>
    </Link>
  );
}

function EventDetail({ e }: { e: TraceEvent }) {
  const fields: [string, ReactNode][] = [["time", <><Time iso={e.ts} kind="stamp" /> · <Time iso={e.ts} kind="time" zone /></>], ["model", e.model ?? "—"], ["latency", e.latency_ms ? `${e.latency_ms} ms` : "—"]];
  const tokens = e.summary_out.match(/tokens in=(\d+|None) out=(\d+|None)/);
  if (tokens) fields.push(["tokens", `in ${tokens[1]} · out ${tokens[2]}`]);
  return (
    <Card className="h-fit lg:sticky lg:top-8">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="t-title">{e.agent} · {e.kind}</h2>
        <span className="ml-auto"><Badge tone={e.ok ? "ok" : "error"}>{e.ok ? "ok" : "failed"}</Badge></span>
      </div>
      <dl className="mb-4 flex flex-col gap-2">
        {fields.map(([k, v]) => (
          <div key={k} className="t-mono-sm flex gap-3"><dt className="text-fg-3">{k}</dt><dd className="ml-auto truncate text-right">{v}</dd></div>
        ))}
      </dl>
      {[["input", e.summary_in], ["output", e.summary_out]].map(([label, text]) => (
        <div key={label} className="mb-4 flex flex-col gap-2">
          <span className="t-label text-fg-3">{label}</span>
          <pre className="t-mono-sm max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md border border-line bg-inset p-3 text-fg-2">{text}</pre>
        </div>
      ))}
      {e.agent === "critic" && e.kind === "llm_call" && (
        <p className="t-small text-fg-3">The harness recomputes “passed” from these scores and the threshold; the model’s own verdict is ignored.</p>
      )}
    </Card>
  );
}
