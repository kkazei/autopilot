"use client";

/**
 * @author: @kokonutui
 * @description: AI Agent Lanes
 * @version: 1.0.0
 * @date: 2026-10-21
 * @license: MIT
 * @website: https://kokonutui.com
 * @github: https://github.com/kokonut-labs/kokonutui
 *
 * Adapted from KokonutUI's AI Agent Lanes (MIT) for Autopilot's trace. Kept: lanes on a shared clock, replay with a
 * playhead, the scrubber, hover tips and the per-lane step list. Changed: the pipeline is sequential (harness, writer,
 * critic), so the lead/sub-agent connectors are gone; bars come from real trace events (lib/lanes.ts) and use the
 * project's status tokens; clicking a bar opens that event; a live run follows the clock instead of replaying.
 */

import { Pause, Play, RotateCcw } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";

import type { Lane, LaneStep, StepTone } from "@/lib/lanes";
import { toLanes } from "@/lib/lanes";
import type { TraceEvent } from "@/lib/parse";
import { cn } from "@/lib/utils";

const EASE_OUT = [0.23, 1, 0.32, 1] as const;
const LANE_H = 32;
/** A finished run replays in about this many seconds, however long it really took. */
const REPLAY_S = 3.5;

const TONE: Record<StepTone, string> = {
  model: "bg-info",
  "model-failed": "bg-err",
  guard: "bg-ok",
  "guard-failed": "bg-err",
  wait: "bg-warn/70",
  tool: "bg-fg",
  decision: "bg-[repeating-linear-gradient(135deg,var(--text-tertiary)_0_2px,transparent_2px_5px)] ring-1 ring-inset ring-fg-3/40",
  "decision-failed": "bg-[repeating-linear-gradient(135deg,var(--status-error)_0_2px,transparent_2px_5px)] ring-1 ring-inset ring-err/50",
};
const LEGEND: [StepTone, string][] = [["model", "model call"], ["model-failed", "failed"], ["guard", "guardrail"], ["wait", "waiting for you"], ["tool", "tool"], ["decision", "decision"]];

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
const fmt = (s: number) => (s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`);

export default function RunLanes({ events, live = false, selected, onSelect, compact = false, className }: {
  events: TraceEvent[];
  /** A run still going: the playhead sits at the end and the view grows as events arrive. */
  live?: boolean;
  selected?: number;
  onSelect?: (index: number) => void;
  compact?: boolean;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const { lanes, total } = useMemo(() => toLanes(events), [events]);
  const [now, setNow] = useState(live || reduceMotion ? total : 0);
  const [playing, setPlaying] = useState(false);
  const [lane, setLane] = useState<string | null>(null);
  const [hover, setHover] = useState<{ lane: number; step: number } | null>(null);
  const nowRef = useRef(now);
  nowRef.current = now;

  // A finished run plays itself once; a live one just follows the newest event.
  useEffect(() => {
    if (live || reduceMotion) {
      setNow(total);
      return;
    }
    const id = setTimeout(() => setPlaying(true), 300);
    return () => clearTimeout(id);
  }, [live, reduceMotion, total]);

  useEffect(() => {
    if (!playing || total <= 0) return;
    const speed = Math.max(1, total / REPLAY_S);
    let frame = 0;
    let last = performance.now();
    const tick = (t: number) => {
      const next = Math.min(total, nowRef.current + ((t - last) / 1000) * speed);
      last = t;
      setNow(next);
      if (next >= total) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, total]);

  if (lanes.length === 0) return <p className="t-small text-fg-3">No events yet.</p>;

  const done = now >= total;
  const x = (t: number) => `${(t / total) * 100}%`;
  const hoverStep = hover ? lanes[hover.lane]?.steps[hover.step] : undefined;
  const shownLane = lanes.find((l) => l.id === lane) ?? null;
  const toggle = () => {
    if (done) {
      setNow(0);
      setPlaying(true);
    } else setPlaying((p) => !p);
  };

  return (
    <div className={cn("w-full", className)}>
      <div className="mb-2 flex items-center gap-3">
        <span className="t-mono-sm text-fg-3">{live ? `live · ${fmt(total)}` : done ? `${fmt(total)} total` : `${fmt(now)} / ${fmt(total)}`}</span>
        {!compact && (
          <ul className="hidden flex-wrap items-center gap-3 md:flex">
            {LEGEND.map(([t, label]) => (
              <li key={t} className="t-small flex items-center gap-1.5 text-fg-3"><span className={cn("h-2 w-3 rounded-[2px]", TONE[t])} />{label}</li>
            ))}
          </ul>
        )}
        {!live && (
          <button type="button" onClick={toggle} aria-label={done ? "Replay run" : playing ? "Pause" : "Play"}
            className="ml-auto flex size-7 items-center justify-center rounded-md border border-line text-fg-2 transition-colors hover:bg-raised hover:text-fg">
            {done ? <RotateCcw className="size-3.5" /> : playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </button>
        )}
      </div>

      <div className="flex">
        <ul className="w-16 shrink-0 sm:w-20">
          {lanes.map((l) => (
            <li key={l.id} style={{ height: LANE_H }} className="flex items-center">
              <button type="button" onClick={() => setLane(lane === l.id ? null : l.id)} aria-pressed={lane === l.id}
                className={cn("t-mono-sm -ml-1.5 rounded-md px-1.5 py-0.5 text-left transition-colors", lane === l.id ? "bg-raised text-fg" : "text-fg-2 hover:text-fg")}>
                {l.name}
              </button>
            </li>
          ))}
        </ul>
        <div className="relative min-w-0 flex-1">
          {lanes.map((l, li) => (
            <div key={l.id} className="relative border-b border-dashed border-line last:border-b-0" style={{ height: LANE_H }}>
              {l.steps.map((s, si) => (
                <Bar key={s.index} step={s} now={now} left={x(s.start)} width={x(s.end - s.start)} selected={selected === s.index}
                  onHover={(on) => setHover(on ? { lane: li, step: si } : null)} onSelect={onSelect && (() => onSelect(s.index))} />
              ))}
            </div>
          ))}
          <div aria-hidden className="pointer-events-none absolute inset-y-0 w-px bg-fg/70" style={{ left: x(Math.min(now, total)) }} />
          <AnimatePresence>
            {hoverStep && hover && now > hoverStep.start && <Tip key={`${hover.lane}-${hover.step}`} step={hoverStep} top={hover.lane * LANE_H} total={total} />}
          </AnimatePresence>
        </div>
      </div>

      {!live && (
        <div className="flex items-center">
          <span className="w-16 shrink-0 sm:w-20" />
          <div className="relative min-w-0 flex-1 pt-2 pb-1">
            <input type="range" aria-label="Run time" aria-valuetext={fmt(now)} min={0} max={total} step={0.05} value={now}
              onChange={(e) => {
                setPlaying(false);
                setNow(Number(e.target.value));
              }}
              className="peer absolute inset-x-0 top-0 h-5 w-full cursor-ew-resize opacity-0" />
            <div className="h-px w-full bg-line" />
            <span aria-hidden className="pointer-events-none absolute top-[5px] size-[7px] -translate-x-1/2 rounded-full bg-fg peer-focus-visible:ring-2 peer-focus-visible:ring-info"
              style={{ left: `${(now / total) * 100}%` }} />
          </div>
        </div>
      )}

      {!compact && shownLane && <LaneSteps lane={shownLane} now={now} onSelect={onSelect} />}
    </div>
  );
}

function Bar({ step, now, left, width, selected, onHover, onSelect }: {
  step: LaneStep; now: number; left: string; width: string; selected: boolean; onHover: (on: boolean) => void; onSelect?: () => void;
}) {
  const progress = clamp01((now - step.start) / (step.end - step.start));
  if (progress <= 0) return null;
  const style: CSSProperties = { left, width };
  return (
    <button type="button" aria-label={step.label} onClick={onSelect} onPointerEnter={() => onHover(true)} onPointerLeave={() => onHover(false)}
      onFocus={() => onHover(true)} onBlur={() => onHover(false)} style={style}
      className={cn("absolute top-1/2 h-3.5 min-w-[3px] -translate-y-1/2 rounded-[3px] px-px outline-hidden focus-visible:ring-2 focus-visible:ring-info",
        selected && "ring-2 ring-info ring-offset-1 ring-offset-surface", onSelect ? "cursor-pointer" : "cursor-default")}>
      <span className={cn("block h-full origin-left rounded-[2px]", TONE[step.tone])} style={{ width: `${progress * 100}%` }} />
    </button>
  );
}

function Tip({ step, top, total }: { step: LaneStep; top: number; total: number }) {
  const anchor: CSSProperties = (step.start + step.end) / 2 / total > 0.6 ? { right: `${(1 - step.end / total) * 100}%` } : { left: `${(step.start / total) * 100}%` };
  return (
    <motion.div initial={{ opacity: 0, y: 3 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: { duration: 0.08 } }} transition={{ duration: 0.14, ease: EASE_OUT }}
      className="pointer-events-none absolute z-20 w-64 -translate-y-full rounded-md border border-line-strong bg-raised px-3 py-2 shadow-lg" style={{ ...anchor, top: top + 2 }}>
      <p className="t-mono-sm flex justify-between gap-2 text-fg-3"><span>{step.detail || "instant"}</span><span>{fmt(step.end - step.start)}</span></p>
      <p className="t-small mt-0.5 break-words text-fg">{step.label}</p>
    </motion.div>
  );
}

function LaneSteps({ lane, now, onSelect }: { lane: Lane; now: number; onSelect?: (index: number) => void }) {
  const steps = lane.steps.filter((s) => now >= s.start);
  return (
    <ol className="mt-3 flex flex-col gap-1 border-t border-line pt-3">
      {steps.map((s) => (
        <li key={s.index}>
          <button type="button" onClick={onSelect && (() => onSelect(s.index))} className="flex w-full items-baseline gap-2 text-left hover:opacity-80">
            <span className={cn("size-1.5 shrink-0 translate-y-[-1px] rounded-full", TONE[s.tone])} />
            <span className="t-small min-w-0 flex-1 truncate text-fg-2">{s.label}</span>
            <span className="t-mono-sm text-fg-3">{s.detail}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}
