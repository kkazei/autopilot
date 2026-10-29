"use client";

import { ArrowRight, Check, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import HoldButton from "./kokonutui/hold-button";
import RunLanes from "./kokonutui/run-lanes";
import { useLive } from "./live";
import { EASE_OUT } from "./motion";
import { Time } from "./time";
import { Badge, buttonClass, Card, cx, Dot, GuardChip, Icon, ScoreTile } from "./ui";
import { shortRun } from "@/lib/format";
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

function Flash({ msg }: { msg: { ok: boolean; text: string } | null }) {
  return (
    <AnimatePresence mode="popLayout">
      {msg && (
        <motion.span key={msg.text} role="status" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
          className={cx("t-small", msg.ok ? "text-fg-2" : "text-err")}>
          {msg.text}
        </motion.span>
      )}
    </AnimatePresence>
  );
}

/** Why the run buttons are disabled, or undefined when they are not. */
function useRunBlock(pending: boolean) {
  const { live } = useLive();
  if (!live) return "Checking the backend…";
  if (live.backend !== "up") return "The backend is asleep; it wakes in about a minute.";
  if (live.status?.running) return "A run is going.";
  if (pending) return "Starting…";
  return undefined;
}

export function RunButtons() {
  const { act } = useLive();
  const [pending, setPending] = useState<string | null>(null);
  const [msg, setMsg] = useFlash();
  const why = useRunBlock(pending !== null);
  const start = async (id: string, body: Record<string, unknown>) => {
    setPending(id);
    const r = await act({ action: "run", ...body });
    setMsg({ ok: r.ok, text: r.message });
    setPending(null);
  };
  return (
    <div className="grid w-full grid-cols-2 items-center gap-2 sm:flex sm:w-auto sm:flex-wrap" title={why}>
      <span className="col-span-2 empty:hidden sm:order-none"><Flash msg={msg} /></span>
      <button className={buttonClass("primary", "col-span-2 h-11 rounded-xl sm:order-last sm:h-9 sm:rounded-md")} disabled={Boolean(why)} onClick={() => start("next", { kind: "next" })}>
        {pending === "next" ? "Starting…" : "Run next post"}
      </button>
      <button className={buttonClass("secondary", "h-10 rounded-xl sm:h-9 sm:rounded-md")} disabled={Boolean(why)} onClick={() => start("plan", { kind: "plan" })}>Plan next week</button>
      <button className={buttonClass("ghost", "h-10 rounded-xl border border-line sm:order-first sm:h-9 sm:rounded-md sm:border-transparent")} disabled={Boolean(why)} onClick={() => start("dry", { kind: "next", dry_run: true })}>Dry run</button>
    </div>
  );
}

/** The daily schedule's measure-only run, on demand: reads engagement and saves learnings, never drafts or posts. */
export function MeasureButton({ kind = "secondary" }: { kind?: "secondary" | "ghost" }) {
  const { act } = useLive();
  const [pending, setPending] = useState(false);
  const [msg, setMsg] = useFlash();
  const why = useRunBlock(pending);
  const start = async () => {
    setPending(true);
    const r = await act({ action: "run", kind: "measure" });
    setMsg({ ok: r.ok, text: r.message });
    setPending(false);
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-2" title={why ?? "Reads likes, reposts and replies now and saves learnings: at most 4 model requests, no drafts, nothing posted"}>
      <Flash msg={msg} />
      <button className={buttonClass(kind)} disabled={Boolean(why)} onClick={start}>
        <Icon name="refresh" size={14} className={cx(pending && "animate-spin")} />
        {pending ? "Starting…" : "Measure now"}
      </button>
    </span>
  );
}

const GOALS = ["engagement", "awareness", "click"] as const;

/** One post on a topic of your choosing (scripts/run_post.py): the same critic, guardrails, rate cap and approval. */
export function TopicForm() {
  const { act } = useLive();
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const [angle, setAngle] = useState("");
  const [goal, setGoal] = useState<(typeof GOALS)[number]>("engagement");
  const [dry, setDry] = useState(true);
  const [pending, setPending] = useState(false);
  const [msg, setMsg] = useFlash();
  const why = useRunBlock(pending);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;
    setPending(true);
    const r = await act({ action: "run", kind: "topic", topic: topic.trim(), angle: angle.trim() || undefined, goal, dry_run: dry });
    setMsg({ ok: r.ok, text: r.message });
    setPending(false);
    if (r.ok) {
      setTopic("");
      setAngle("");
      setOpen(false);
    }
  };

  const field = "w-full rounded-md border border-line bg-inset px-3 py-2 text-sm text-fg placeholder:text-fg-3 focus:border-line-strong focus:outline-hidden";
  return (
    <Card>
      <div className="flex items-center gap-3">
        <div className="flex min-w-0 flex-col">
          <h2 className="t-title">Write about a topic</h2>
          <span className="t-small text-fg-2">Outside the weekly plan; same critic, guardrails and approval.</span>
        </div>
        <button className={buttonClass(open ? "ghost" : "secondary", "ml-auto shrink-0 whitespace-nowrap")} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Close" : "New post"}
        </button>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.form key="form" onSubmit={submit} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: EASE_OUT }} className="overflow-hidden">
            <div className="grid gap-3 pt-4 md:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="t-label text-fg-3">topic</span>
                <input className={field} value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={200} required placeholder="Rye crust on a cold morning" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="t-label text-fg-3">angle · optional</span>
                <input className={field} value={angle} onChange={(e) => setAngle(e.target.value)} maxLength={300} placeholder="one concrete detail a beginner would notice" />
              </label>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div role="radiogroup" aria-label="goal" className="flex rounded-md border border-line p-0.5">
                {GOALS.map((g) => (
                  <button key={g} type="button" role="radio" aria-checked={goal === g} onClick={() => setGoal(g)}
                    className={cx("t-mono-sm relative rounded-[5px] px-3 py-1", goal === g ? "text-fg" : "text-fg-3 hover:text-fg-2")}>
                    {goal === g && <motion.span layoutId="goal-pill" className="absolute inset-0 rounded-[5px] bg-raised" transition={{ duration: 0.2, ease: EASE_OUT }} />}
                    <span className="relative">{g}</span>
                  </button>
                ))}
              </div>
              <label className="t-small flex items-center gap-2 text-fg-2">
                <input type="checkbox" checked={dry} onChange={(e) => setDry(e.target.checked)} className="size-4 accent-[var(--status-info)]" />
                dry run (publishes nothing)
              </label>
              <div className="ml-auto flex items-center gap-3" title={why}>
                <Flash msg={msg} />
                <button type="submit" className={buttonClass("primary")} disabled={Boolean(why) || !topic.trim()}>
                  {pending ? "Starting…" : dry ? "Start dry run" : "Start"}
                </button>
              </div>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
      {!open && <Flash msg={msg} />}
    </Card>
  );
}

const SCORE_LABEL: Record<(typeof SCORE_KEYS)[number], string> = { voice: "voice", clarity: "clarity", cta: "cta", policy_risk: "policy risk" };
const mmss = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

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

  const answer = async (choice: "approve" | "not_now" | "reject") => {
    if (!approval) return;
    setBusy(choice);
    const r = await act({ action: "answer", approval_id: approval.id, choice });
    setMsg({ ok: r.ok, text: r.message });
    setBusy(null);
  };

  return (
    <AnimatePresence mode="wait" initial={false}>
      {approval ? (
        <motion.section key={`approval-${approval.id}`} aria-label="Draft waiting for approval"
          initial={{ opacity: 0, y: 12, scale: 0.98, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -8, scale: 0.98, filter: "blur(4px)" }} transition={{ duration: 0.35, ease: EASE_OUT }}
          className="relative flex flex-col gap-4 overflow-hidden rounded-lg border border-warn bg-surface p-4 md:p-5">
          <motion.span aria-hidden className="pointer-events-none absolute inset-0 rounded-lg ring-2 ring-warn/40"
            animate={{ opacity: [0.9, 0.2, 0.9] }} transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }} />
          <ApprovalBody approval={approval} run={live?.run ?? null} now={now} firstSeen={firstSeen.current} busy={busy} msg={msg} answer={answer} />
        </motion.section>
      ) : (
        <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <Card>
            <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
              <Badge tone="neutral">nothing waiting</Badge>
              <span className="t-small text-fg-2">{msg?.text ?? "When a draft passes the critic and every guardrail, it waits here for you."}</span>
            </div>
          </Card>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

type LiveRun = NonNullable<NonNullable<ReturnType<typeof useLive>["live"]>["run"]>;

function ApprovalBody({ approval, run, now, firstSeen, busy, msg, answer }: {
  approval: { id: number; prompt: string; dry_run: boolean }; run: LiveRun | null; now: number; firstSeen: Map<number, number>;
  busy: string | null; msg: { ok: boolean; text: string } | null; answer: (c: "approve" | "not_now" | "reject") => void;
}) {
  const draft = parseApprovalPrompt(approval.prompt);
  // The prompt opens right after the last pre-approval guardrail, so its timestamp survives a page reload.
  const opened = run?.events.findLast((e) => e.kind === "guardrail" && e.summary_in.startsWith("check_duplicate"))?.ts;
  const start = opened ? Date.parse(opened) : firstSeen.get(approval.id) ?? now;
  const waited = Math.max(0, Math.floor((now - start) / 1000));
  const left = Math.max(0, APPROVAL_TIMEOUT_S - waited);
  const writer = run?.events.findLast((e) => e.agent === "writer" && e.kind === "llm_call" && e.ok);
  const critic = run?.events.findLast((e) => e.agent === "critic" && e.kind === "llm_call" && e.ok);
  const stagger = { shown: { transition: { staggerChildren: 0.05, delayChildren: 0.15 } } };
  const item = { hidden: { opacity: 0, y: 6 }, shown: { opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE_OUT } } };

  return (
    <>
      <div className="relative flex flex-wrap items-center gap-3">
        <Badge tone="warn">{approval.dry_run ? "needs you · dry run" : "needs you"}</Badge>
        {run && (
          <Link href={`/runs/${run.run_id}`} className="t-mono-sm inline-flex items-center gap-1 text-fg-2 hover:text-fg">
            {shortRun(run.run_id)} <ArrowRight className="size-3" /> trace
          </Link>
        )}
        <span className="t-mono-sm ml-auto inline-flex items-center gap-1 text-warn">
          <Icon name="clock" size={14} /> {mmss(waited)} / 15:00
        </span>
      </div>
      <div className="relative flex flex-col gap-3 rounded-md border border-line bg-inset px-4 py-3 md:px-5 md:py-4">
        <p className="t-body-lg whitespace-pre-wrap break-words">{draft?.text ?? approval.prompt}</p>
        <div className="t-mono-sm flex flex-wrap gap-x-4 gap-y-1 text-fg-3">
          {draft && <span className={draft.chars > MAX_POST_CHARS - 20 ? "text-warn" : undefined}>{draft.chars} / {MAX_POST_CHARS} chars</span>}
          {writer && <span>writer {shortModel(writer.model)}</span>}
          {critic && <span>critic {shortModel(critic.model)}</span>}
        </div>
      </div>
      {run?.critique && (
        <>
          <span className="t-label relative text-fg-3">critic · passes at 4+ on every score</span>
          <motion.div className="relative grid grid-cols-2 gap-2 lg:grid-cols-4" initial="hidden" animate="shown" variants={stagger}>
            {SCORE_KEYS.map((k) => (
              <motion.div key={k} variants={item} className="min-w-0">
                <ScoreTile label={SCORE_LABEL[k]} score={run.critique!.scores[k]} reason={run.critique!.reasons[k]} />
              </motion.div>
            ))}
          </motion.div>
        </>
      )}
      {run && run.guardrails.length > 0 && (
        <motion.div className="relative flex flex-wrap items-center gap-2" initial="hidden" animate="shown" variants={stagger}>
          <span className="t-label text-fg-3">guardrails</span>
          {run.guardrails.map((g) => (
            <motion.span key={g.name} variants={item}><GuardChip ok={g.ok} label={g.name} title={g.detail} /></motion.span>
          ))}
        </motion.div>
      )}
      <div className="relative flex flex-col gap-2 sm:flex-row sm:items-center">
        {approval.dry_run ? (
          <button className={buttonClass("primary", "w-full sm:w-auto")} disabled={busy !== null} onClick={() => answer("approve")}>
            <Check className="size-4" /> {busy === "approve" ? "Approving…" : "Approve (dry run)"}
          </button>
        ) : (
          <HoldButton className="w-full sm:w-auto" disabled={busy !== null} holdingLabel="Keep holding to publish" completeLabel="Publishing…"
            resetAfter={0} onHoldComplete={() => answer("approve")}>
            Hold to publish
          </HoldButton>
        )}
        <div className="flex gap-2">
          <button className={buttonClass("secondary", "flex-1 sm:flex-none")} disabled={busy !== null} onClick={() => answer("not_now")}>Not now</button>
          <button className={buttonClass("danger", "flex-1 sm:flex-none")} disabled={busy !== null} onClick={() => answer("reject")}><X className="size-4" /> Reject</button>
        </div>
        <span className={cx("t-small sm:ml-auto", msg && !msg.ok ? "text-err" : "text-fg-3")}>
          {msg?.text ?? (left > 0 ? `No answer in ${mmss(left)} carries the post forward.` : "Timed out: the post is carried forward.")}
        </span>
      </div>
    </>
  );
}

/** The run happening now, or the last one: its timeline, the newest steps, and the way into the full trace. */
export function LatestRun() {
  const { live } = useLive();
  const router = useRouter();
  const run = live?.run;
  const status = live?.status;
  const running = Boolean(status?.running);
  const exit = status && !running ? status.exit_code : null;
  const steps = (run?.events ?? []).map((e, i) => [e, i] as const).slice(-6);
  return (
    <Card>
      <div className="mb-4 flex items-center gap-2">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span key={running ? `run-${status!.what}` : `exit-${exit}`} initial={{ opacity: 0, y: 6, filter: "blur(3px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -6, filter: "blur(3px)" }} transition={{ duration: 0.22, ease: EASE_OUT }}>
            {running ? <Badge tone="info">running · {status!.what}</Badge>
              : exit !== null && exit !== undefined ? <Badge tone={exitTone(exit)}>{EXIT_MEANINGS[exit] ?? `exit ${exit}`}</Badge>
              : <Badge tone="neutral">last run</Badge>}
          </motion.span>
        </AnimatePresence>
        {run && <span className="t-mono-sm ml-auto text-fg-3">{shortRun(run.run_id)}</span>}
      </div>
      {!run ? <p className="t-small text-fg-3">No runs yet.</p> : (
        <>
          <RunLanes events={run.events} live={!run.finished} compact
            onSelect={(i) => router.push(`/runs/${run.run_id}?e=${i}`)} />
          <ol className="mt-4 flex flex-col gap-2">
            <AnimatePresence initial={false}>
              {steps.map(([e, i]) => (
                <motion.li key={i} layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25, ease: EASE_OUT }}
                  className="flex items-center gap-2">
                  <Dot tone={e.ok ? "ok" : "error"} />
                  <Time iso={e.ts} kind="time" className="t-mono-sm text-fg-3" />
                  <span className="t-small min-w-0 flex-1 truncate">{stepLabel(e)}</span>
                  {e.latency_ms ? <span className="t-mono-sm text-fg-3">{(e.latency_ms / 1000).toFixed(1)}s</span> : null}
                </motion.li>
              ))}
              {status?.approval && (
                <motion.li key="waiting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                  <motion.span animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.4, repeat: Infinity }}><Dot tone="warn" /></motion.span>
                  <span className="t-small text-warn">waiting for your approval</span>
                </motion.li>
              )}
            </AnimatePresence>
          </ol>
          <Link href={`/runs/${run.run_id}`} className={buttonClass("secondary", "mt-4 w-full")}>
            Open full trace <ArrowRight className="size-4" />
          </Link>
        </>
      )}
    </Card>
  );
}
