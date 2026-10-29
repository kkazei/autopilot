"use client";

import { Activity, CalendarDays, LayoutDashboard, Lightbulb, LogOut, PanelLeftClose, PanelLeftOpen, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { signOut } from "next-auth/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { useLive } from "./live";
import { LogoMark } from "./logo";
import { EASE_OUT } from "./motion";
import { SystemLights } from "./system-lights";
import { cx } from "./ui";
import { NAV_COOKIE } from "@/lib/nav";

type Item = { href: string; label: string; icon: LucideIcon };
const ITEMS: Item[] = [
  { href: "/control", label: "Control", icon: LayoutDashboard },
  { href: "/plan", label: "Plan", icon: CalendarDays },
  { href: "/runs", label: "Traces", icon: Activity },
  { href: "/learnings", label: "Learnings", icon: Lightbulb },
];
const isActive = (path: string, href: string) => path.startsWith(href);
const SPRING = { type: "spring", bounce: 0.2, duration: 0.5 } as const;
const FADE = { duration: 0.18, ease: EASE_OUT } as const;

/** Live state on the nav itself: amber when a draft needs you (the logo's dot), blue while a run is going. Only
 * "needs you" pulses; a running run is a steady light, since nothing loops for decoration (docs/DESIGN.md). */
function useBadges(): Partial<Record<string, "warn" | "info">> {
  const s = useLive().live?.status;
  if (s?.approval) return { "/control": "warn" };
  if (s?.running) return { "/runs": "info" };
  return {};
}

function Pulse({ tone, className }: { tone: "warn" | "info"; className?: string }) {
  const bg = tone === "warn" ? "bg-warn" : "bg-info";
  return (
    <span className={cx("relative flex size-2", className)} aria-hidden>
      {tone === "warn" && <span className={cx("absolute inset-0 animate-ping rounded-full opacity-60 motion-reduce:animate-none", bg)} />}
      <span className={cx("relative size-2 rounded-full", bg)} />
    </span>
  );
}

/** The glass panel clips its children and sets a containing block, so tips render into body beside their anchor. */
function Tip({ label, show, children }: { label: ReactNode; show: boolean; children: (bind: object) => ReactNode }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  const open = (e: { currentTarget: Element }) => {
    const r = e.currentTarget.getBoundingClientRect();
    setAt({ x: r.right + 12, y: r.top + r.height / 2 });
  };
  const close = () => setAt(null);
  return (
    <>
      {children({ onMouseEnter: open, onMouseLeave: close, onFocus: open, onBlur: close })}
      {typeof document !== "undefined" && createPortal(
        <AnimatePresence>
          {show && at && (
            <motion.span role="tooltip" initial={{ opacity: 0, x: -4, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: -4 }}
              transition={FADE} style={{ left: at.x, top: at.y }}
              className="glass t-small pointer-events-none fixed z-50 -translate-y-1/2 whitespace-nowrap rounded-lg px-2.5 py-1 text-fg">
              {label}
            </motion.span>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}

function useShortcut() {
  const [mac, setMac] = useState(false);
  useEffect(() => setMac(/Mac|iPhone|iPad/.test(navigator.userAgent)), []);
  return mac ? "⌘B" : "Ctrl B";
}

function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="t-mono-sm ml-2 rounded border border-line px-1 text-[10px] text-fg-3">{children}</kbd>;
}

/** Desktop: a floating glass panel. The active item's lens slides between pages; it collapses to icons (Ctrl/⌘ B). */
export function Sidebar({ login, brand, collapsed: initial }: { login: string; brand: string; collapsed: boolean }) {
  const path = usePathname();
  const badges = useBadges();
  const shortcut = useShortcut();
  const [collapsed, setCollapsed] = useState(initial);
  const toggle = useCallback(() => setCollapsed((c) => !c), []);

  useEffect(() => {
    document.cookie = `${NAV_COOKIE}=${collapsed ? "1" : "0"}; path=/; max-age=31536000; samesite=lax`;
  }, [collapsed]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "b") return;
      if ((e.target as HTMLElement).closest("input, textarea, [contenteditable]")) return;
      e.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  const label = (text: ReactNode, className?: string) => (
    <motion.span initial={false} animate={{ opacity: collapsed ? 0 : 1, x: collapsed ? -6 : 0 }} transition={FADE}
      className={cx("relative whitespace-nowrap", className)} aria-hidden={collapsed || undefined}>
      {text}
    </motion.span>
  );

  return (
    <div className="sticky top-0 z-20 hidden h-dvh shrink-0 p-3 md:block">
      <motion.aside initial={false} animate={{ width: collapsed ? 68 : 236 }} transition={SPRING}
        className="glass flex h-full flex-col overflow-hidden rounded-[22px] p-3">
        <div className="relative flex h-11 items-center">
          <Tip label={<>Expand<Kbd>{shortcut}</Kbd></>} show={collapsed}>
            {(bind) => collapsed ? (
              <button {...bind} onClick={toggle} aria-label="Expand the sidebar"
                className="group relative grid size-11 place-items-center rounded-xl transition-colors hover:bg-fg/[0.06]">
                <LogoMark size={24} className="transition-opacity duration-150 group-hover:opacity-0" />
                <PanelLeftOpen className="absolute size-[18px] text-fg-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
              </button>
            ) : (
              <Link href="/control" className="flex items-center gap-2.5 rounded-xl px-2.5 py-1.5">
                <LogoMark size={24} />
                <span className="flex flex-col leading-tight">
                  {label("autopilot", "t-title")}
                  {label(brand, "t-small text-fg-3")}
                </span>
              </Link>
            )}
          </Tip>
          {!collapsed && (
            <Tip label={<>Collapse<Kbd>{shortcut}</Kbd></>} show>
              {(bind) => (
                <motion.button {...bind} onClick={toggle} aria-label="Collapse the sidebar" whileTap={{ scale: 0.9 }}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ...FADE, delay: 0.12 }}
                  className="ml-auto grid size-8 shrink-0 place-items-center rounded-lg text-fg-3 transition-colors hover:bg-fg/[0.06] hover:text-fg">
                  <PanelLeftClose className="size-4" />
                </motion.button>
              )}
            </Tip>
          )}
        </div>

        <div className="mx-1 my-3 h-px bg-line/70" />

        <nav className="flex flex-col gap-1" aria-label="Main">
          {ITEMS.map(({ href, label: text, icon: IconC }, i) => {
            const on = isActive(path, href);
            const badge = badges[href];
            return (
              <Tip key={href} label={text} show={collapsed}>
                {(bind) => (
                  <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 + i * 0.05, duration: 0.35, ease: EASE_OUT }}>
                    <Link {...bind} href={href} aria-current={on ? "page" : undefined} aria-label={collapsed ? text : undefined}
                      className={cx("group relative flex h-10 items-center gap-3 rounded-xl px-[13px] text-sm font-medium transition-colors duration-150",
                        on ? "text-fg" : "text-fg-2 hover:text-fg")}>
                      {on && <motion.span layoutId="side-lens" className="glass-lens absolute inset-0 rounded-xl" transition={SPRING} />}
                      <span aria-hidden className="absolute inset-0 rounded-xl transition-colors duration-150 group-hover:bg-fg/[0.04] group-active:bg-fg/[0.07]" />
                      <motion.span className="relative" whileTap={{ scale: 0.88 }} transition={{ type: "spring", bounce: 0.5, duration: 0.3 }}>
                        <IconC className="size-[18px]" strokeWidth={on ? 2.2 : 1.8} />
                      </motion.span>
                      {label(text)}
                      {badge && <Pulse tone={badge} className={collapsed ? "absolute top-2 left-[29px]" : "ml-auto"} />}
                    </Link>
                  </motion.div>
                )}
              </Tip>
            );
          })}
        </nav>

        <div className="mt-auto flex flex-col gap-2">
          <AnimatePresence initial={false} mode="popLayout">
            {collapsed ? (
              <motion.div key="dot" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={FADE} className="grid h-8 place-items-center">
                <SystemLights dot />
              </motion.div>
            ) : (
              <motion.div key="card" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={FADE}
                className="flex flex-col gap-2 rounded-xl border border-line/70 bg-fg/[0.025] p-3">
                <span className="t-label text-fg-3">system</span>
                <SystemLights />
              </motion.div>
            )}
          </AnimatePresence>
          <div className="flex items-center gap-2.5 rounded-xl p-1.5">
            <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-raised text-xs font-semibold uppercase text-fg-2 ring-1 ring-line">
              {login.slice(0, 1)}
            </span>
            {label(login, "t-small min-w-0 flex-1 truncate text-fg-2")}
            {!collapsed && (
              <Tip label="Sign out" show>
                {(bind) => (
                  <motion.button {...bind} onClick={() => signOut({ callbackUrl: "/login" })} aria-label="Sign out" whileTap={{ scale: 0.9 }}
                    className="grid size-8 shrink-0 place-items-center rounded-lg text-fg-3 transition-colors hover:bg-err-bg hover:text-err">
                    <LogOut className="size-4" />
                  </motion.button>
                )}
              </Tip>
            )}
          </div>
        </div>
      </motion.aside>
    </div>
  );
}

/** Phones: a header that turns to glass once content scrolls under it, and swaps the wordmark for the page title. */
export function MobileHeader() {
  const path = usePathname();
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, "change", (v) => setScrolled(v > 36));
  const title = ITEMS.find((i) => isActive(path, i.href))?.label ?? "autopilot";
  return (
    <header className="sticky top-0 z-20 px-3 pt-[max(0.5rem,env(safe-area-inset-top))] md:hidden">
      <div className={cx("flex h-12 items-center gap-2.5 rounded-2xl border px-3 transition-[background-color,border-color,box-shadow] duration-300",
        scrolled ? "glass" : "border-transparent")}>
        <Link href="/control" aria-label="Autopilot home"><LogoMark size={22} /></Link>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span key={scrolled ? title : "brand"} initial={{ opacity: 0, y: 8, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -8, filter: "blur(4px)" }} transition={{ duration: 0.25, ease: EASE_OUT }} className="t-title">
            {scrolled ? title : "autopilot"}
          </motion.span>
        </AnimatePresence>
        <span className="ml-auto"><SystemLights compact /></span>
      </div>
    </header>
  );
}

/** Phones: a floating glass bar. The lens springs between tabs; scrolling down shrinks it to icons, scrolling up restores it. */
export function TabBar() {
  const path = usePathname();
  const badges = useBadges();
  const { scrollY } = useScroll();
  const [mini, setMini] = useState(false);
  useMotionValueEvent(scrollY, "change", (v) => {
    const delta = v - (scrollY.getPrevious() ?? 0);
    if (v < 48) setMini(false);
    else if (delta > 6) setMini(true);
    else if (delta < -6) setMini(false);
  });

  return (
    <nav aria-label="Main" className="pointer-events-none fixed inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden">
      <motion.div layout transition={SPRING} style={{ borderRadius: 28 }} className="glass pointer-events-auto flex w-full max-w-sm p-1.5">
        {ITEMS.map(({ href, label, icon: IconC }) => {
          const on = isActive(path, href);
          const badge = badges[href];
          return (
            <motion.div key={href} layout transition={SPRING} className="flex-1" whileTap={{ scale: 0.92 }}>
              <Link href={href} aria-current={on ? "page" : undefined} aria-label={label}
                className={cx("relative flex flex-col items-center justify-center gap-0.5 rounded-[22px] transition-[color,height] duration-300",
                  mini ? "h-11" : "h-[52px]", on ? "text-fg" : "text-fg-3")}>
                {on && <motion.span layoutId="tab-lens" className="glass-lens absolute inset-0 rounded-[22px]" transition={SPRING} />}
                <span className="relative">
                  <IconC className="size-5" strokeWidth={on ? 2.2 : 1.8} />
                  {badge && <Pulse tone={badge} className="absolute -top-0.5 -right-1.5" />}
                </span>
                <AnimatePresence initial={false}>
                  {!mini && (
                    <motion.span initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                      transition={FADE} className="relative overflow-hidden text-[11px] leading-4 font-medium">
                      {label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </Link>
            </motion.div>
          );
        })}
      </motion.div>
    </nav>
  );
}
