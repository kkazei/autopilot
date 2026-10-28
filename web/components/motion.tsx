"use client";

import { animate, MotionConfig, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { Children, useEffect, type ReactNode } from "react";

// Purposeful motion (docs/DESIGN.md): things enter once, numbers count to new values, state changes crossfade.
// Everything honours the system's reduce-motion setting.

export const EASE_OUT = [0.23, 1, 0.32, 1] as const;

export function MotionRoot({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user" transition={{ duration: 0.3, ease: EASE_OUT }}>{children}</MotionConfig>;
}

/** Children rise into place one after another, once, on first render. */
export function Reveal({ children, className, step = 0.05 }: { children: ReactNode; className?: string; step?: number }) {
  return (
    <motion.div className={className} initial="hidden" animate="shown" variants={{ shown: { transition: { staggerChildren: step } } }}>
      {Children.map(children, (child) =>
        child == null ? null : (
          <motion.div variants={{ hidden: { opacity: 0, y: 8, filter: "blur(3px)" }, shown: { opacity: 1, y: 0, filter: "blur(0px)" } }}
            transition={{ duration: 0.35, ease: EASE_OUT }} className="min-w-0">
            {child}
          </motion.div>
        ),
      )}
    </motion.div>
  );
}

/** A number that counts from its previous value to the new one. */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? value : 0);
  const text = useTransform(mv, (v) => Math.round(v).toString());
  useEffect(() => {
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, { duration: 0.6, ease: EASE_OUT });
    return () => controls.stop();
  }, [value, mv, reduce]);
  return <motion.span className={className}>{text}</motion.span>;
}
