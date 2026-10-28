"use client";

import { motion } from "motion/react";
import Link from "next/link";

import { cx } from "./ui";

/** Link tabs whose active background slides between options (KokonutUI-style shared layout). */
export function FilterTabs({ id, options }: { id: string; options: { href: string; label: string; count: number; on: boolean }[] }) {
  return (
    <div role="tablist" className="inline-flex w-fit max-w-full flex-wrap self-start rounded-md border border-line bg-surface p-0.5">
      {options.map((o) => (
        <Link key={o.href} href={o.href} role="tab" aria-selected={o.on} scroll={false}
          className={cx("t-mono-sm relative rounded-[5px] px-3 py-1.5 transition-colors", o.on ? "text-fg" : "text-fg-3 hover:text-fg-2")}>
          {o.on && <motion.span layoutId={`tabs-${id}`} className="absolute inset-0 rounded-[5px] bg-raised" transition={{ type: "spring", bounce: 0.18, duration: 0.4 }} />}
          <span className="relative">{o.label} <span className="text-fg-3">{o.count}</span></span>
        </Link>
      ))}
    </div>
  );
}
