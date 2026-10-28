"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useLive } from "./live";
import { Badge, buttonClass, Card, cx, Dot, GuardChip, Icon, ScoreTile } from "./ui";
import { shortRun, utcTime } from "@/lib/format";
import { EXIT_MEANINGS, exitTone, MAX_POST_CHARS, parseApprovalPrompt, SCORE_KEYS, shortModel, stepLabel } from "@/lib/parse";

const APPROVAL_TIMEOUT_S = 15 * 60; // ui/controller.py APPROVAL_TIMEOUT_S

function useFlash() {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 6000);
    return () => clearTimeout(t);
  }, [msg]);
  return [msg, setMsg] as const;
}

export function RunButtons() {
  const { live, act } = useLive();
  const [pending, setPending] = useState<string | null>(null);
  const [msg, setMsg] = useFlash();
  const blocked = !live || live.backend !== "up" || Boolean(live.status?.running) || pending !== null;
  const why = !live ? "Checking the backend…" : live.backend !== "up" ? "The backend is asleep; it wakes in about a minute." : live.status?.running ? "A run is going." : undefined;
  const start = async (id: string, body: Record<string, unknown>) => {
    setPending(id);
    const r = await act({ action: "run", ...body });
    setMsg({ ok: r.ok, text: r.message });
    setPending(null);
  };
  return (
    <div className="flex flex-wrap items-center gap-2" title={why}>
      {msg && <span role="status" className={cx("t-small", msg.ok ? "text-fg-2" : "text-err")}>{msg.text}</span>}
      <button className={buttonClass("ghost")} disabled={blocked} onClick={() => start("dry", { kind: "next", dry_run: true })}>Dry run</button>
      <button className={buttonClass("secondary")} disabled={blocked} onClick={() => start("plan", { kind: "plan" })}>Plan next week</button>
      <button className={buttonClass("primary")} disabled={blocked} onClick={() => start("next", { kind: "next" })}>
        {pending === "next" ? "Starting…" : "Run next post"}
      </button>
    </div>
  );
}

const SCORE_LABEL: Record<(typeof SCORE_KEYS)[number], string> = { voice: "voice", clarity: "clarity", cta: "cta", policy_risk: "policy risk" };

export function ApprovalCard() {
  const { live, act } = useLive();
  const approval = live?.status?.approval ?? null;
  const firstSeen = useRef<Map<number, number>>(new Map());
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useFlash();

  useEffect(() => {
    if (!approval) return;
    if (!firstSeen.current.has(approval.id)) firstSeen.current.set(approval.id, Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [approval]);

  if (!approval) {
    return (
      <Card>
        <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
          <Badge tone="neutral">nothing waiting</Badge>
          <span className="t-small text-fg-2">{msg?.text ?? "When a draft passes the critic and every guardrail, it waits here for you."}</span>
        </div>
      </Card>
    );
  }

  const draft = parseApprovalPrompt(approval.prompt);
  const run = live?.run;
  // The prompt opens right after the last pre-approval guardrail, so its timestamp survives a page reload.
  const opened = run?.events.findLast((e) => e.kind === "guardrail" && e.summary_in.startsWith("check_duplicate"))?.ts;
  const start = opened ? Date.parse(opened) : firstSeen.current.get(approval.id) ?? now;
  const waited = Math.max(0, Math.floor((now - start) / 1000));
  const left = Math.max(0, APPROVAL_TIMEOUT_S - waited);
  const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const writer = run?.events.findLast((e) => e.agent === "writer" && e.kind === "llm_call" && e.ok);
  const critic = run?.events.findLast((e) => e.agent === "critic" && e.kind === "llm_call" && e.ok);
  const answer = async (choice: "approve" | "not_now" | "reject") => {
    setBusy(choice);
    const r = await act({ action: "answer", approval_id: approval.id, choice });
    setMsg({ ok: r.ok, text: r.message });
    setBusy(null);
  };

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-warn bg-surface p-4 md:p-5" aria-label="Draft waiting for approval">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone="warn">{approval.dry_run ? "needs you · dry run" : "needs you"}</Badge>
        {run && <span className="t-mono-sm hidden text-fg-2 sm:inline">{shortRun(run.run_id)}</span>}
        <span className="t-mono-sm ml-auto inline-flex items-center gap-1 text-warn">
          <Icon name="clock" size={14} /> {mmss(waited)} / 15:00
        </span>
      </div>
      <div className="flex flex-col gap-3 rounded-md border border-line bg-inset px-4 py-3 md:px-5 md:py-4">
        <p className="t-body-lg whitespace-pre-wrap break-words">{draft?.text ?? approval.prompt}</p>
        <div className="t-mono-sm flex flex-wrap gap-x-4 gap-y-1 text-fg-3">
          {draft && <span>{draft.chars} / {MAX_POST_CHARS} chars</span>}
          {writer && <span>writer {shortModel(writer.model)}</span>}
          {critic && <span>critic {shortModel(critic.model)}</span>}
        </div>
      </div>
      {run?.critique && (
        <>
          <span className="t-label text-fg-3">critic · passes at 4+ on every score</span>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            {SCORE_KEYS.map((k) => (
              <ScoreTile key={k} label={SCORE_LABEL[k]} score={run.critique!.scores[k]} reason={run.critique!.reasons[k]} />
            ))}
          </div>
        </>
      )}
      {run && run.guardrails.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="t-label text-fg-3">guardrails</span>
          {run.guardrails.map((g) => <GuardChip key={g.name} ok={g.ok} label={g.name} title={g.detail} />)}
        </div>
      )}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <button className={buttonClass("primary", "w-full sm:w-auto")} disabled={busy !== null} onClick={() => answer("approve")}>
          {busy === "approve" ? "Publishing…" : approval.dry_run ? "Approve (dry run)" : "Approve & publish"}
        </button>
        <div className="flex gap-2">
          <button className={buttonClass("secondary", "flex-1 sm:flex-none")} disabled={busy !== null} onClick={() => answer("not_now")}>Not now</button>
          <button className={buttonClass("danger", "flex-1 sm:flex-none")} disabled={busy !== null} onClick={() => answer("reject")}>Reject</button>
        </div>
        <span className={cx("t-small sm:ml-auto", msg && !msg.ok ? "text-err" : "text-fg-3")}>
          {msg?.text ?? (left > 0 ? `No answer in ${mmss(left)} carries the post forward.` : "Timed out: the post is carried forward.")}
        </span>
      </div>
    </section>
  );
}

export function LiveRun() {
  const { live } = useLive();
  const run = live?.run;
  const status = live?.status;
  const running = Boolean(status?.running);
  const exit = status && !running ? status.exit_code : null;
  const steps = (run?.events ?? []).slice(-8);
  return (
    <Card>
      <div className="mb-4 flex items-center gap-2">
        {running ? <Badge tone="info">running · {status!.what}</Badge>
          : exit !== null && exit !== undefined ? <Badge tone={exitTone(exit)}>{EXIT_MEANINGS[exit] ?? `exit ${exit}`}</Badge>
          : <Badge tone="neutral">last run</Badge>}
        {run && <span className="t-mono-sm ml-auto text-fg-3">{shortRun(run.run_id)}</span>}
      </div>
      {steps.length === 0 ? <p className="t-small text-fg-3">No runs yet.</p> : (
        <ol className="flex flex-col gap-2">
          {steps.map((e, i) => (
            <li key={`${e.ts}-${i}`} className="flex items-center gap-2">
              <Dot tone={e.ok ? "ok" : "error"} />
              <span className="t-mono-sm text-fg-3">{utcTime(e.ts)}</span>
              <span className="t-small min-w-0 flex-1 truncate">{stepLabel(e)}</span>
              {e.latency_ms ? <span className="t-mono-sm text-fg-3">{(e.latency_ms / 1000).toFixed(1)}s</span> : null}
            </li>
          ))}
          {status?.approval && (
            <li className="flex items-center gap-2">
              <Dot tone="warn" />
              <span className="t-small text-warn">waiting for your approval</span>
            </li>
          )}
        </ol>
      )}
      {run && <Link href={`/runs/${run.run_id}`} className={buttonClass("ghost", "mt-3 -ml-3")}>Open trace →</Link>}
    </Card>
  );
}
