"use client";

import { Activity, CalendarDays, LayoutDashboard, Lightbulb, LogOut, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll, useSpring, useTransform, type MotionValue } from "motion/react";
import { signOut } from "next-auth/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode, type SyntheticEvent } from "react";
import { createPortal } from "react-dom";

import { useLive } from "./live";
import { LogoMark } from "./logo";
import { EASE_OUT } from "./motion";
import { SystemLights } from "./system-lights";
import { ThemeCycle, ThemeSegmented } from "./theme-toggle";
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
const FADE = { duration: 0.18, ease: EASE_OUT } as const;
const LENS = { stiffness: 520, damping: 38, mass: 0.7 };
const HOLD_MS = 260;
const W_OPEN = 236;
const W_SHUT = 68;

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

/** The GitHub photo for the allowlisted login (both sign-in methods use it); the initial if it cannot load. */
export function Avatar({ login, size = 32 }: { login: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <span aria-hidden style={{ width: size, height: size }} className="grid shrink-0 place-items-center rounded-full bg-raised text-xs font-semibold uppercase text-fg-2 ring-1 ring-line">
        {login.slice(0, 1)}
      </span>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element -- a 32px remote avatar; the image optimizer would add a hop for nothing
  return <img src={`https://avatars.githubusercontent.com/${encodeURIComponent(login)}?s=${size * 2}`} alt="" width={size} height={size}
    onError={() => setFailed(true)} className="shrink-0 rounded-full bg-raised ring-1 ring-line" />;
}

/** The matte panel clips its children and sets a containing block, so tips render into body beside their anchor. */
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
              className="matte t-small pointer-events-none fixed z-50 -translate-y-1/2 whitespace-nowrap rounded-lg px-2.5 py-1 text-fg">
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

/**
 * One matte lens shared by a group of nav links. It moves the moment a link is pressed (the server render follows),
 * and, as on iOS, pressing and holding lifts it so it can be dragged across the items; letting go opens the one under it.
 */
function useLensNav(axis: "x" | "y") {
  const path = usePathname();
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  useEffect(() => setPending(null), [path]);
  const pendingIdx = pending ? ITEMS.findIndex((i) => i.href === pending) : -1;
  const active = pendingIdx >= 0 ? pendingIdx : ITEMS.findIndex((i) => isActive(path, i.href));

  const box = useRef<HTMLDivElement>(null);
  const items = useRef<(HTMLAnchorElement | null)[]>([]);
  const pos = useSpring(0, LENS);
  const size = useSpring(0, LENS);
  const scale = useSpring(1, { stiffness: 400, damping: 22 });
  const [held, setHeld] = useState(false);
  const [over, setOver] = useState(-1);
  const g = useRef({ timer: 0, x: 0, y: 0, last: 0, id: -1, held: false, suppress: false, measured: false, active });
  g.current.active = active;

  const span = (i: number): [number, number] => {
    const el = items.current[i];
    if (!el) return [0, 0];
    return axis === "x" ? [el.offsetLeft, el.offsetWidth] : [el.offsetTop, el.offsetHeight];
  };
  const snap = (i: number, jump: boolean) => {
    if (i < 0) return size.jump(0);
    const [p, s] = span(i);
    if (jump) { pos.jump(p); size.jump(s); } else { pos.set(p); size.set(s); }
  };
  const nearest = (c: number) => {
    let best = 0;
    let d = Infinity;
    ITEMS.forEach((_, i) => {
      const [p, s] = span(i);
      if (Math.abs(p + s / 2 - c) < d) { d = Math.abs(p + s / 2 - c); best = i; }
    });
    return best;
  };
  const follow = (c: number) => {
    const i = nearest(c);
    setOver(i);
    const [, s] = span(i);
    pos.set(Math.min(Math.max(c - s / 2, span(0)[0]), span(ITEMS.length - 1)[0]));
    size.set(s);
  };
  const coord = (e: PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    return axis === "x" ? e.clientX - r.left : e.clientY - r.top;
  };

  useLayoutEffect(() => {
    if (!g.current.held) snap(active, !g.current.measured);
    g.current.measured = true;
  });
  useEffect(() => {
    const ro = new ResizeObserver(() => { if (!g.current.held) snap(g.current.active, true); });
    if (box.current) ro.observe(box.current);
    items.current.forEach((el) => el && ro.observe(el));
    return () => ro.disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- refs only

  const end = (commit: boolean) => {
    window.clearTimeout(g.current.timer);
    if (!g.current.held) return;
    g.current.held = false;
    g.current.suppress = true;
    window.setTimeout(() => { g.current.suppress = false; }, 350);
    setHeld(false);
    scale.set(1);
    const i = commit ? nearest(g.current.last) : g.current.active;
    snap(i, false);
    if (commit && i !== g.current.active) {
      setPending(ITEMS[i].href);
      router.push(ITEMS[i].href);
    }
  };

  const handlers = {
    onPointerDown: (e: PointerEvent) => {
      if (e.button !== 0) return;
      const s = g.current;
      s.x = e.clientX; s.y = e.clientY; s.last = coord(e); s.id = e.pointerId;
      window.clearTimeout(s.timer);
      s.timer = window.setTimeout(() => {
        s.held = true;
        setHeld(true);
        scale.set(axis === "x" ? 1.14 : 1.04);
        try { box.current?.setPointerCapture(s.id); } catch { /* the pointer already left */ }
        navigator.vibrate?.(8);
        follow(s.last);
      }, HOLD_MS);
    },
    onPointerMove: (e: PointerEvent) => {
      const s = g.current;
      s.last = coord(e);
      if (s.held) follow(s.last);
      else if (Math.hypot(e.clientX - s.x, e.clientY - s.y) > 8) window.clearTimeout(s.timer);
    },
    onPointerUp: () => end(true),
    onPointerCancel: () => end(false),
    onClickCapture: (e: SyntheticEvent) => {
      if (!g.current.suppress) return;
      e.preventDefault();
      e.stopPropagation();
      g.current.suppress = false;
    },
    onContextMenu: (e: SyntheticEvent) => e.preventDefault(), // a long press is ours, not the link menu
  };
  const link = (i: number) => ({
    ref: (el: HTMLAnchorElement | null) => { items.current[i] = el; },
    onClick: () => setPending(ITEMS[i].href),
    draggable: false,
  });
  // While held, the item under the lens reads as current, as on iOS.
  return { box, active: held && over >= 0 ? over : active, held, pos, size, scale, handlers, link };
}

function Lens({ axis, pos, size, scale, held, className }: { axis: "x" | "y"; pos: MotionValue<number>; size: MotionValue<number>; scale: MotionValue<number>; held: boolean; className: string }) {
  return (
    <motion.span aria-hidden style={axis === "x" ? { x: pos, width: size, scale } : { y: pos, height: size, scale }}
      className={cx("matte-lens pointer-events-none absolute transition-[background-color,box-shadow] duration-200", className,
        held && "bg-fg/10 shadow-[0_10px_28px_-10px_rgb(0_0_0/0.55)]")} />
  );
}

/**
 * Desktop: a floating matte panel. Its edge is the resize handle: drag it and the labels fade with the width, letting go
 * snaps open or shut; a click on the edge (or Ctrl/⌘ B) toggles it. The width is kept in a cookie so it loads right.
 */
export function Sidebar({ login, brand, collapsed: initial }: { login: string; brand: string; collapsed: boolean }) {
  const badges = useBadges();
  const shortcut = useShortcut();
  const lens = useLensNav("y");
  const [collapsed, setCollapsed] = useState(initial);
  const [dragging, setDragging] = useState(false);
  const width = useSpring(initial ? W_SHUT : W_OPEN, { stiffness: 380, damping: 36 });
  const labels = useTransform(width, [W_SHUT + 30, W_OPEN - 50], [0, 1]);
  const drag = useRef<{ x: number; w: number; moved: boolean } | null>(null);

  const settle = (shut: boolean) => {
    width.set(shut ? W_SHUT : W_OPEN);
    setCollapsed(shut);
  };
  useEffect(() => {
    document.cookie = `${NAV_COOKIE}=${collapsed ? "1" : "0"}; path=/; max-age=31536000; samesite=lax`;
  }, [collapsed]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "b") return;
      if ((e.target as HTMLElement).closest("input, textarea, [contenteditable]")) return;
      e.preventDefault();
      settle(width.get() > (W_SHUT + W_OPEN) / 2);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const edge = {
    onPointerDown: (e: PointerEvent<HTMLButtonElement>) => {
      if (e.button !== 0) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      drag.current = { x: e.clientX, w: width.get(), moved: false };
    },
    onPointerMove: (e: PointerEvent) => {
      const d = drag.current;
      if (!d) return;
      const dx = e.clientX - d.x;
      if (!d.moved && Math.abs(dx) > 3) { d.moved = true; setDragging(true); }
      if (!d.moved) return;
      const w = d.w + dx;
      // Past either end the panel resists, like a rubber band, instead of stopping dead.
      width.jump(w > W_OPEN ? W_OPEN + (w - W_OPEN) * 0.15 : w < W_SHUT ? W_SHUT - (W_SHUT - w) * 0.15 : w);
    },
    onPointerUp: () => {
      const d = drag.current;
      drag.current = null;
      setDragging(false);
      if (d) settle(d.moved ? width.get() < (W_SHUT + W_OPEN) / 2 : !collapsed);
    },
  };

  const label = (text: ReactNode, className?: string) => (
    <motion.span style={{ opacity: labels }} className={cx("relative whitespace-nowrap", className)} aria-hidden={collapsed || undefined}>{text}</motion.span>
  );

  return (
    <div className="group/side sticky top-0 z-20 hidden h-dvh shrink-0 p-3 md:block">
      <motion.aside style={{ width }} className="matte flex h-full flex-col overflow-hidden rounded-[22px] p-3">
        <Link href="/control" aria-label="Autopilot, Control" className="flex h-11 items-center gap-2.5 rounded-xl pl-[10px]">
          <LogoMark size={24} className="shrink-0" />
          <span className="flex flex-col leading-tight">
            {label("autopilot", "t-title")}
            {label(brand, "t-small text-fg-3")}
          </span>
        </Link>

        <div className="mx-1 my-3 h-px bg-line/70" />

        <nav aria-label="Main" ref={lens.box} {...lens.handlers} className="relative flex select-none flex-col gap-1">
          <Lens axis="y" {...lens} className="inset-x-0 top-0 rounded-xl" />
          {ITEMS.map(({ href, label: text, icon: IconC }, i) => {
            const on = i === lens.active;
            const badge = badges[href];
            return (
              <Tip key={href} label={text} show={collapsed && !lens.held}>
                {(bind) => (
                  <Link {...bind} {...lens.link(i)} href={href} aria-current={on ? "page" : undefined} aria-label={collapsed ? text : undefined}
                    className={cx("group relative flex h-10 items-center gap-3 rounded-xl px-[13px] text-sm font-medium transition-colors duration-150",
                      on ? "text-fg" : "text-fg-2 hover:text-fg")}>
                    <span aria-hidden className="absolute inset-0 rounded-xl transition-colors duration-150 group-hover:bg-fg/[0.04]" />
                    <motion.span className="relative" whileTap={{ scale: 0.88 }} transition={{ type: "spring", bounce: 0.5, duration: 0.3 }}>
                      <IconC className="size-[18px]" strokeWidth={on ? 2.2 : 1.8} />
                    </motion.span>
                    {label(text)}
                    {badge && <Pulse tone={badge} className={collapsed ? "absolute top-2 left-[29px]" : "ml-auto"} />}
                  </Link>
                )}
              </Tip>
            );
          })}
        </nav>

        <div className="mt-auto flex flex-col gap-2">
          <AnimatePresence initial={false} mode="popLayout">
            {collapsed ? (
              <motion.div key="shut" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={FADE} className="flex flex-col items-center gap-1">
                <span className="grid h-8 place-items-center"><SystemLights dot /></span>
                <ThemeCycle />
              </motion.div>
            ) : (
              <motion.div key="open" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={FADE} className="flex flex-col gap-2">
                <div className="flex flex-col gap-2 rounded-xl border border-line/70 bg-fg/[0.025] p-3">
                  <span className="t-label text-fg-3">system</span>
                  <SystemLights />
                </div>
                <ThemeSegmented id="side" />
              </motion.div>
            )}
          </AnimatePresence>
          <div className="flex items-center gap-2.5 rounded-xl py-1.5 pl-[6px]">
            <Avatar login={login} />
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

      <Tip label={<>{collapsed ? "Drag or click to expand" : "Drag or click to collapse"}<Kbd>{shortcut}</Kbd></>} show={!dragging}>
        {(bind) => (
          <button {...bind} {...edge} type="button" aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"} aria-expanded={!collapsed}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); settle(!collapsed); } }}
            className="group/edge absolute inset-y-6 right-0 z-10 w-3 cursor-col-resize touch-none">
            <span aria-hidden className={cx("absolute top-1/2 right-[4px] h-12 w-1 -translate-y-1/2 rounded-full bg-fg-3 transition-[opacity,height] duration-200",
              dragging ? "h-16 opacity-100" : "opacity-0 group-hover/side:opacity-30 group-hover/edge:h-16 group-hover/edge:opacity-80 group-focus-visible/edge:opacity-80")} />
          </button>
        )}
      </Tip>
    </div>
  );
}

/** Phones: the photo opens a small matte sheet with the theme and sign out. */
function AccountMenu({ login }: { login: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <motion.button whileTap={{ scale: 0.9 }} onClick={() => setOpen((o) => !o)} aria-label="Account and theme" aria-expanded={open}
        className="grid size-9 place-items-center rounded-full">
        <Avatar login={login} size={28} />
      </motion.button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, scale: 0.9, y: -6, filter: "blur(6px)" }} animate={{ opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.95, y: -4, filter: "blur(4px)" }} transition={{ type: "spring", bounce: 0.25, duration: 0.35 }}
            style={{ transformOrigin: "top right" }} className="matte absolute top-11 right-0 flex w-60 flex-col gap-3 rounded-2xl p-3">
            <div className="flex items-center gap-3">
              <Avatar login={login} size={36} />
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-medium">{login}</span>
                <span className="t-small text-fg-3">owner</span>
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="t-label text-fg-3">theme</span>
              <ThemeSegmented id="menu" />
            </div>
            <button onClick={() => signOut({ callbackUrl: "/login" })}
              className="flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-medium text-err transition-colors hover:bg-err-bg active:bg-err-bg">
              <LogOut className="size-4" /> Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Progressive blur: stacked backdrop blurs, each masked to a shorter band from the top, so the blur is strongest at the
// screen edge and fades to nothing below the header. Opacity on an ancestor would cut the backdrop off, so it stays on.
const BLUR_LAYERS: [number, number, number][] = [[1, 55, 100], [2, 40, 85], [4, 25, 70], [8, 10, 55], [16, 0, 40]];

function ProgressiveBlur() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[calc(100%+2rem)]">
      {BLUR_LAYERS.map(([px, from, to]) => {
        const mask = `linear-gradient(to bottom, black ${from}%, transparent ${to}%)`;
        return <div key={px} className="absolute inset-0" style={{ backdropFilter: `blur(${px}px)`, WebkitBackdropFilter: `blur(${px}px)`, maskImage: mask, WebkitMaskImage: mask }} />;
      })}
      <div className="absolute inset-0 bg-linear-to-b from-canvas/85 via-canvas/40 to-transparent" />
    </div>
  );
}

/** Phones: no box around the header; content scrolling under it melts into a progressive blur. Once scrolled, the
 * wordmark gives way to the page title. */
export function MobileHeader({ login }: { login: string }) {
  const path = usePathname();
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, "change", (v) => setScrolled(v > 36));
  const title = ITEMS.find((i) => isActive(path, i.href))?.label ?? "autopilot";
  return (
    <header className="sticky top-0 z-20 md:hidden">
      <ProgressiveBlur />
      <div className="relative flex h-14 items-center gap-2.5 pt-[env(safe-area-inset-top)] pr-2 pl-4">
        <Link href="/control" aria-label="Autopilot, Control"><LogoMark size={22} /></Link>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span key={scrolled ? title : "brand"} initial={{ opacity: 0, y: 8, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -8, filter: "blur(4px)" }} transition={{ duration: 0.25, ease: EASE_OUT }} className="t-title">
            {scrolled ? title : "autopilot"}
          </motion.span>
        </AnimatePresence>
        <span className="ml-auto"><SystemLights compact /></span>
        <AccountMenu login={login} />
      </div>
    </header>
  );
}

/** Phones: a floating matte bar. A tap moves the lens at once; press and hold lifts it to drag between tabs; scrolling
 * down shrinks the bar to icons and scrolling up restores it. */
export function TabBar() {
  const badges = useBadges();
  const lens = useLensNav("x");
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
      <div ref={lens.box} {...lens.handlers}
        className="matte pointer-events-auto relative flex w-full max-w-sm touch-none select-none rounded-[28px] p-1.5 [-webkit-touch-callout:none]">
        <Lens axis="x" {...lens} className="top-1.5 bottom-1.5 left-0 rounded-[22px]" />
        {ITEMS.map(({ href, label, icon: IconC }, i) => {
          const on = i === lens.active;
          const badge = badges[href];
          return (
            <Link key={href} {...lens.link(i)} href={href} aria-current={on ? "page" : undefined} aria-label={label}
              className={cx("relative flex flex-1 flex-col items-center justify-center gap-0.5 rounded-[22px] transition-[color,height,transform] duration-300 active:scale-95",
                mini ? "h-11" : "h-[52px]", on ? "text-fg" : "text-fg-3")}>
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
          );
        })}
      </div>
    </nav>
  );
}
