"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { EASE_OUT } from "./motion";
import { cx, Icon, type IconName } from "./ui";

const ITEMS: [string, string, IconName][] = [["/control", "Control", "dashboard"], ["/plan", "Plan", "calendar"], ["/runs", "Traces", "activity"], ["/learnings", "Learnings", "bulb"]];
const isActive = (path: string, href: string) => path.startsWith(href);
const SLIDE = { type: "spring", bounce: 0.18, duration: 0.45 } as const;

/** The active item's background is one shared element that slides to whichever page you open. */
export function SideNav() {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-1">
      {ITEMS.map(([href, label, icon], i) => {
        const on = isActive(path, href);
        return (
          <motion.div key={href} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 + i * 0.04, duration: 0.3, ease: EASE_OUT }}>
            <Link href={href} aria-current={on ? "page" : undefined}
              className={cx("group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors", on ? "text-fg" : "text-fg-2 hover:text-fg")}>
              {on && <motion.span layoutId="sidenav-active" className="absolute inset-0 rounded-md bg-raised" transition={SLIDE} />}
              <span className="absolute inset-0 rounded-md bg-raised/0 transition-colors group-hover:bg-raised/40" aria-hidden />
              <motion.span className="relative" whileHover={{ scale: 1.12, rotate: -4 }} transition={{ duration: 0.2 }}><Icon name={icon} /></motion.span>
              <span className="relative">{label}</span>
              {on && <motion.span layoutId="sidenav-dot" className="relative ml-auto size-1.5 rounded-full bg-warn" transition={SLIDE} />}
            </Link>
          </motion.div>
        );
      })}
    </nav>
  );
}

export function TabBar() {
  const path = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-10 flex justify-between border-t border-line bg-surface/90 px-6 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md md:hidden">
      {ITEMS.map(([href, label, icon]) => {
        const on = isActive(path, href);
        return (
          <Link key={href} href={href} aria-current={on ? "page" : undefined}
            className={cx("relative flex flex-col items-center gap-1 px-2 t-small transition-colors", on ? "text-fg" : "text-fg-3")}>
            {on && <motion.span layoutId="tab-active" className="absolute -top-2 h-0.5 w-8 rounded-full bg-warn" transition={SLIDE} />}
            <motion.span animate={{ scale: on ? 1.1 : 1, y: on ? -1 : 0 }} transition={{ duration: 0.25, ease: EASE_OUT }}>
              <Icon name={icon} size={20} />
            </motion.span>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
