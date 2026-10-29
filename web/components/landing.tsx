"use client";

import {
  ArrowRight, Ban, CalendarDays, ChartColumn, Copy, EyeOff, Gauge, Lightbulb, PenLine, Repeat, RotateCcw, Scale,
  Send, ShieldCheck, Timer, UserCheck, type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { GitHubMark } from "./github-mark";
import DotField from "./kokonutui/dot-field";
import DynamicText from "./kokonutui/dynamic-text";
import HoldButton from "./kokonutui/hold-button";
import RunLanes from "./kokonutui/run-lanes";
import { LogoMark, Wordmark } from "./logo";
import { ThemeCycle } from "./theme-toggle";
import { EASE_OUT } from "./motion";
import { Badge, buttonClass, cx, GuardChip, ScoreTile } from "./ui";
import { SAMPLE_RUN } from "@/lib/sample-run";

export const REPO_URL = "https://github.com/kkazei/autopilot";

// Facts about the example run, computed from it so the page never claims more than the trace shows.
const llm = SAMPLE_RUN.filter((e) => e.kind === "llm_call");
const guards = SAMPLE_RUN.filter((e) => e.kind === "guardrail");
const waitStart = SAMPLE_RUN.findLast((e) => e.summary_in === "check_duplicate")?.ts;
const waitEnd = SAMPLE_RUN.find((e) => e.summary_in === "require_approval")?.ts;
const WAIT_S = waitStart && waitEnd ? Math.round((Date.parse(waitEnd) - Date.parse(waitStart)) / 1000) : 0;

const rise = { hidden: { opacity: 0, y: 14, filter: "blur(4px)" }, shown: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.5, ease: EASE_OUT } } };
const stagger = (s = 0.08) => ({ hidden: {}, shown: { transition: { staggerChildren: s } } });

function InView({ children, className, step }: { children: ReactNode; className?: string; step?: number }) {
  return (
    <motion.div className={className} initial="hidden" whileInView="shown" viewport={{ once: true, margin: "-80px" }} variants={stagger(step)}>
      {children}
    </motion.div>
  );
}

function SectionHead({ title, sub }: { title: ReactNode; sub: ReactNode }) {
  return (
    <motion.div variants={rise} className="mx-auto mb-10 flex max-w-2xl flex-col items-center gap-3 text-center md:mb-14">
      <h2 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">{title}</h2>
      <p className="text-base text-fg-2 text-pretty md:text-lg">{sub}</p>
    </motion.div>
  );
}

function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-line/60 bg-canvas/70 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4 md:px-6">
        <Link href="/" aria-label="Autopilot home"><Wordmark size={22} /></Link>
        <nav className="ml-auto flex items-center gap-1 sm:gap-2">
          <a href="#how" className={buttonClass("ghost", "hidden sm:inline-flex")}>How it works</a>
          <a href={REPO_URL} className={buttonClass("ghost")} target="_blank" rel="noreferrer"><GitHubMark /> <span className="hidden sm:inline">GitHub</span></a>
          <ThemeCycle />
          <Link href="/login" className={buttonClass("secondary")}>Sign in</Link>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <DotField className="min-h-[calc(100dvh-3.5rem)] px-4 py-16 md:px-6" spacing={20}>
      <motion.div initial="hidden" animate="shown" variants={stagger(0.09)}
        className="relative z-10 mx-auto grid w-full max-w-6xl items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)]">
        <div className="flex flex-col items-start gap-6">
          <motion.h1 variants={rise} className="text-5xl font-semibold tracking-tight text-balance text-fg md:text-6xl lg:text-7xl">
            A week of posts, on&nbsp;autopilot.
          </motion.h1>
          <motion.p variants={rise} className="text-xl text-fg-2 md:text-2xl">
            Autopilot{" "}
            <DynamicText className="font-medium text-fg" interval={1900}
              words={["plans the week", "writes every draft", "critiques its own work", "waits for your yes", "publishes to Bluesky", "learns what works"]} />
          </motion.p>
          <motion.p variants={rise} className="max-w-xl text-base text-fg-2 text-pretty md:text-lg">
            A team of AI agents that plans a week of social posts from your brand brief, writes and scores each draft, checks it
            against your rules, and publishes only after you approve it. Then it reads the engagement and plans the next week
            with what it learned.
          </motion.p>
          <motion.div variants={rise} className="flex flex-wrap items-center gap-3">
            <a href="#how" className={buttonClass("primary", "h-11 px-5 text-base")}>See how it works <ArrowRight className="size-4" /></a>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className={buttonClass("secondary", "h-11 px-5 text-base")}><GitHubMark /> View the code</a>
          </motion.div>
        </div>
        <motion.div variants={rise} className="relative">
          <div className="rounded-xl border border-line bg-surface/90 p-4 shadow-[0_30px_100px_-30px_rgb(0_0_0/0.6)] backdrop-blur-md md:p-5">
            <div className="mb-4 flex items-center gap-2">
              <span className="flex gap-1.5" aria-hidden>{["bg-err", "bg-warn", "bg-ok"].map((c) => <span key={c} className={cx("size-2.5 rounded-full opacity-70", c)} />)}</span>
              <span className="t-mono-sm ml-2 text-fg-3">example run · one post, start to finish</span>
            </div>
            <RunLanes events={SAMPLE_RUN} compact />
            <div className="mt-4 grid grid-cols-3 gap-2">
              {[[llm.length, "model calls"], [guards.length, "checks"], [`${WAIT_S}s`, "waiting for you"]].map(([v, l]) => (
                <div key={String(l)} className="rounded-md border border-line bg-inset px-3 py-2">
                  <div className="t-mono text-fg">{v}</div>
                  <div className="t-small text-fg-3">{l}</div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </DotField>
  );
}

const STEPS: [LucideIcon, string, string, boolean?][] = [
  [CalendarDays, "Plan", "Drafts a week of posts from your brand brief and last week's learnings."],
  [PenLine, "Write", "Writes each post in your voice, under 300 characters, with one clear call to action."],
  [Scale, "Critique", "A second model scores voice, clarity, call to action and risk. One weak score sends it back."],
  [ShieldCheck, "Check", "Length, banned phrases, rate cap and duplicates are checked by code, not by the model."],
  [UserCheck, "You approve", "Nothing goes out until you hold to publish. Ignore it and the post simply waits.", true],
  [Send, "Publish", "Posts to Bluesky, re-running every check on the exact text first."],
  [ChartColumn, "Measure", "A daily job reads likes, reposts and replies on posts old enough to judge."],
  [Lightbulb, "Learn", "Turns engagement into one-line lessons the next week's plan has to use."],
];

/** The steps as a track, not a card grid: nodes on one line (two rows of four on desktop, a column on phones), the owner's
 * step lit amber, and a return to Plan, because the loop is the point. */
function Loop() {
  return (
    <section id="how" className="scroll-mt-16 px-4 py-20 md:px-6 md:py-28">
      <InView className="mx-auto max-w-6xl">
        <SectionHead title="One loop, every week" sub="Eight steps from brand brief to lessons learned. You are one of them." />
        <motion.ol variants={stagger(0.06)} className="grid gap-y-8 lg:grid-cols-4 lg:gap-x-6 lg:gap-y-14">
          {STEPS.map(([Icon, title, body, you], i) => {
            const rowEnd = i % 4 === 3;
            const last = i === STEPS.length - 1;
            return (
              <motion.li key={title} variants={rise} className="relative pl-14 lg:pt-14 lg:pl-0">
                {!last && <span aria-hidden className="absolute top-10 bottom-[-2rem] left-[19px] w-px bg-line lg:hidden" />}
                {!rowEnd && <span aria-hidden className="absolute top-5 right-[-1.5rem] left-10 hidden h-px bg-line lg:block" />}
                <span className={cx("absolute top-0 left-0 grid size-10 place-items-center rounded-full border",
                  you ? "border-warn bg-warn-bg text-warn shadow-[0_0_0_6px_var(--status-warn-bg)]" : "border-line-strong bg-canvas text-fg-2")}>
                  <Icon className="size-4" />
                </span>
                <div className="flex flex-col gap-1.5">
                  <h3 className={cx("t-title flex items-center gap-2", you && "text-warn")}>
                    {title}{you && <LogoMark size={16} className="text-fg-2" />}
                  </h3>
                  <p className="text-sm text-fg-2 text-pretty">{body}</p>
                </div>
              </motion.li>
            );
          })}
        </motion.ol>
        <motion.p variants={rise} className="t-small mt-10 flex items-center gap-2 text-fg-3 lg:justify-end">
          <RotateCcw className="size-3.5" /> then back to Plan, with the lessons in hand
        </motion.p>
      </InView>
    </section>
  );
}

function Record() {
  return (
    <section className="border-y border-line bg-surface/40 px-4 py-20 md:px-6 md:py-28">
      <InView className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <motion.div variants={rise} className="flex flex-col gap-4">
          <h2 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">See exactly what the agents did</h2>
          <p className="text-fg-2 text-pretty">
            Every model call, tool call, check and decision is written to a trace, with secrets removed before it is saved. Replay
            a run, open any step, and see which model answered and how long it took.
          </p>
          <ul className="t-small flex flex-col gap-2 text-fg-2">
            <li className="flex gap-2"><Repeat className="mt-0.5 size-4 shrink-0 text-info" /> Free models hit rate limits; Autopilot backs off and falls back to the next model on its own.</li>
            <li className="flex gap-2"><Gauge className="mt-0.5 size-4 shrink-0 text-info" /> A hard daily cap keeps it inside the free tier.</li>
            <li className="flex gap-2"><EyeOff className="mt-0.5 size-4 shrink-0 text-info" /> Keys and passwords are redacted from every trace.</li>
          </ul>
        </motion.div>
        <motion.div variants={rise} className="rounded-xl border border-line bg-surface p-4 md:p-6">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <h3 className="t-title">Example run</h3>
            <Badge tone="ok">done</Badge>
            <span className="t-mono-sm ml-auto text-fg-3">{llm.length} model calls · {llm.filter((e) => !e.ok).length} rate-limited and retried · {guards.length} checks</span>
          </div>
          <RunLanes events={SAMPLE_RUN} />
        </motion.div>
      </InView>
    </section>
  );
}

const SAMPLE_DRAFT = "There is a quiet joy in watching the sourdough dough finally pull away from the bowl. It is a slow process, and we welcome every mistake along the way. Join us this Saturday.";

function DemoApproval() {
  const [done, setDone] = useState(false);
  return (
    <motion.div variants={rise} className="relative flex flex-col gap-4 overflow-hidden rounded-xl border border-warn bg-surface p-5">
      <motion.span aria-hidden className="pointer-events-none absolute inset-0 rounded-xl ring-2 ring-warn/40"
        animate={{ opacity: [0.9, 0.2, 0.9] }} transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }} />
      <div className="relative flex items-center gap-2">
        <Badge tone="warn">needs you</Badge>
        <span className="t-mono-sm ml-auto text-fg-3">try it: nothing is posted</span>
      </div>
      <p className="relative rounded-md border border-line bg-inset px-4 py-3 t-body-lg">{SAMPLE_DRAFT}</p>
      <div className="relative grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[["voice", 5], ["clarity", 5], ["cta", 4], ["policy risk", 5]].map(([l, s]) => <ScoreTile key={String(l)} label={String(l)} score={Number(s)} />)}
      </div>
      <div className="relative flex flex-wrap gap-2">
        {["length", "banned phrases", "rate cap", "duplicate"].map((g) => <GuardChip key={g} ok label={g} />)}
      </div>
      <div className="relative flex flex-col gap-2 sm:flex-row sm:items-center">
        <HoldButton className="w-full sm:w-auto" holdingLabel="Keep holding…" completeLabel="Approved" resetAfter={2600} onHoldComplete={() => {
          setDone(true);
          setTimeout(() => setDone(false), 2600);
        }}>Hold to publish</HoldButton>
        <span className="t-small text-fg-3" aria-live="polite">
          {done ? "In the real app, this is the moment it posts to Bluesky." : "A tap does nothing. You have to mean it."}
        </span>
      </div>
    </motion.div>
  );
}

const RULES: [LucideIcon, string, string][] = [
  [Scale, "The critic can't pass itself", "Scores come from a model; the pass or fail is computed by code from those scores."],
  [Ban, "Banned words stay banned", "Your brand's banned phrases are caught in any spelling, before and again at publish time."],
  [Timer, "A rate cap it can't argue with", "At most three posts a day and an hour between them, counted from what actually went out."],
  [Copy, "No repeats", "Near-duplicates of recent posts are refused, even with new punctuation."],
  [Repeat, "Three tries, then a person", "A draft that can't pass after three revisions goes to you instead of looping."],
  [UserCheck, "Silence means no", "No answer, a closed tab or a timeout carries the post forward. It never posts by default."],
];

function Guardrails() {
  return (
    <section className="px-4 py-20 md:px-6 md:py-28">
      <InView className="mx-auto max-w-6xl">
        <SectionHead title="It never posts on its own" sub="The agents write. Code decides what is allowed. You decide what goes out." />
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <DemoApproval />
          <motion.ul variants={stagger(0.05)} className="flex flex-col divide-y divide-line border-y border-line">
            {RULES.map(([Icon, title, body]) => (
              <motion.li key={title} variants={rise} className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3 gap-y-1 py-4">
                <Icon className="mt-0.5 size-4 text-fg-2" />
                <h3 className="text-sm font-medium">{title}</h3>
                <p className="t-small col-start-2 text-fg-2 text-pretty">{body}</p>
              </motion.li>
            ))}
          </motion.ul>
        </div>
      </InView>
    </section>
  );
}

const STACK: [string, string, string][] = [
  ["Models", "OpenRouter free models, with a fallback chain when one is busy", "OpenRouter"],
  ["Harness", "The loop, the checks and every publish, in Python", "Render"],
  ["Database", "Plans, posts, learnings and traces", "Neon"],
  ["This app", "Approving posts and reading traces, from a phone or a desk", "Vercel"],
  ["Measuring", "Reads engagement every day, or on demand with Measure now", "GitHub Actions"],
];

/** The $0 claim as a bill: each piece, where it runs, what it costs, and the total. */
function Stack() {
  return (
    <section className="border-t border-line bg-surface/40 px-4 py-20 md:px-6 md:py-28">
      <InView className="mx-auto max-w-4xl">
        <SectionHead title={<>Built to run for <span className="text-ok">$0</span> a month</>}
          sub="Every piece sits on a free tier, and a hard cap of 50 model requests a day keeps it there." />
        <motion.div variants={rise} className="overflow-hidden rounded-xl border border-line bg-surface">
          <ul className="divide-y divide-line">
            {STACK.map(([piece, what, where]) => (
              <li key={piece} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-6 gap-y-1 px-5 py-4 sm:grid-cols-[7rem_minmax(0,1fr)_8rem_2.5rem]">
                <span className="text-sm font-medium">{piece}</span>
                <span className="t-small col-span-2 row-start-2 text-fg-2 sm:col-span-1 sm:row-start-auto">{what}</span>
                <span className="t-mono-sm hidden text-fg-3 sm:block">{where}</span>
                <span className="t-mono col-start-2 row-start-1 text-right text-fg-2 sm:col-start-auto sm:row-start-auto">$0</span>
              </li>
            ))}
          </ul>
          <div className="flex items-baseline gap-4 border-t border-line-strong bg-raised/60 px-5 py-4">
            <span className="text-sm font-medium">Per month</span>
            <span className="t-small text-fg-3">capped at 50 model requests a day</span>
            <span className="t-mono ml-auto text-lg font-medium text-ok">$0</span>
          </div>
        </motion.div>
      </InView>
    </section>
  );
}

function Closing() {
  return (
    <section className="px-4 py-20 md:px-6 md:py-28">
      <InView className="mx-auto flex max-w-3xl flex-col items-center gap-6 text-center">
        <motion.div variants={rise}><LogoMark size={56} draw /></motion.div>
        <motion.h2 variants={rise} className="text-3xl font-semibold tracking-tight text-balance md:text-5xl">Let the agents do the week. Keep the last word.</motion.h2>
        <motion.div variants={rise} className="flex flex-wrap justify-center gap-3">
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={buttonClass("primary", "h-11 px-5 text-base")}><GitHubMark /> View the code</a>
          <Link href="/login" className={buttonClass("secondary", "h-11 px-5 text-base")}>Sign in</Link>
        </motion.div>
      </InView>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-line px-4 py-8 md:px-6">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4">
        <Wordmark size={18} />
        <span className="t-small text-fg-3">Built by kkazei · {new Date().getFullYear()}</span>
        <nav className="t-small ml-auto flex gap-4 text-fg-2">
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-fg">GitHub</a>
          <Link href="/login" className="hover:text-fg">Sign in</Link>
        </nav>
      </div>
    </footer>
  );
}

export function Landing() {
  return (
    <div className="min-h-dvh bg-canvas text-fg">
      <Nav />
      <main>
        <Hero />
        <Loop />
        <Record />
        <Guardrails />
        <Stack />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
