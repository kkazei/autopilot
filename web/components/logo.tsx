"use client";

import { motion } from "motion/react";

import { EASE_OUT } from "./motion";

// The Autopilot mark: the agent loop (plan, write, critique, publish, learn) around an amber dot, the human who
// approves every post. Monochrome in the current text colour; the dot is always the "needs you" amber.
export const LOOP_ARC = "M25.2 12.2A10 10 0 1 0 26 17";
export const LOOP_HEAD = "M26.6 7.6v5.2h-5.2";

export function LogoMark({ size = 24, draw = false, className }: { size?: number; draw?: boolean; className?: string }) {
  const stroke = { stroke: "currentColor", strokeWidth: 2.6, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className={className}>
      <motion.path d={LOOP_ARC} {...stroke} initial={draw ? { pathLength: 0 } : false} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: EASE_OUT }} />
      <motion.path d={LOOP_HEAD} {...stroke} initial={draw ? { opacity: 0 } : false} animate={{ opacity: 1 }} transition={{ delay: 0.75, duration: 0.25 }} />
      <motion.circle cx="16" cy="16" r="3.8" fill="var(--status-warn)" initial={draw ? { scale: 0 } : false} animate={{ scale: 1 }}
        transition={{ delay: 0.55, type: "spring", bounce: 0.5, duration: 0.6 }} style={{ transformOrigin: "16px 16px" }} />
    </svg>
  );
}

export function Wordmark({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <LogoMark size={size} />
      <span className="t-title tracking-tight">autopilot</span>
    </span>
  );
}
