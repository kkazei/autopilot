"use client";

import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState, type MouseEvent } from "react";

import { EASE_OUT } from "./motion";
import { cx } from "./ui";
import { THEME_COOKIE, type ThemeChoice } from "@/lib/theme";

const OPTIONS: [ThemeChoice, string, LucideIcon][] = [["system", "System", Monitor], ["light", "Light", Sun], ["dark", "Dark", Moon]];

function current(): ThemeChoice {
  const t = document.documentElement.dataset.theme;
  return t === "light" || t === "dark" ? t : "system";
}

function apply(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  document.cookie = `${THEME_COOKIE}=${choice}; path=/; max-age=31536000; samesite=lax`;
}

/** The new theme grows as a circle from where you clicked; without View Transitions or with reduced motion it just swaps. */
function switchTheme(choice: ThemeChoice, e?: MouseEvent) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } };
  if (!doc.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) return apply(choice);
  const x = e?.clientX ?? innerWidth / 2;
  const y = e?.clientY ?? innerHeight / 2;
  const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  doc.startViewTransition(() => apply(choice)).ready.then(() => {
    document.documentElement.animate({ clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
      { duration: 480, easing: "cubic-bezier(0.23, 1, 0.32, 1)", pseudoElement: "::view-transition-new(root)" });
  });
}

function useTheme() {
  const [theme, setTheme] = useState<ThemeChoice>("system");
  useEffect(() => setTheme(current()), []);
  const choose = (choice: ThemeChoice, e?: MouseEvent) => {
    if (choice === theme) return;
    setTheme(choice);
    switchTheme(choice, e);
  };
  return [theme, choose] as const;
}

/** Three options with a sliding lens, for the expanded sidebar and the phone menu. */
export function ThemeSegmented({ id, className }: { id: string; className?: string }) {
  const [theme, choose] = useTheme();
  return (
    <div role="radiogroup" aria-label="Theme" className={cx("flex rounded-xl border border-line/70 bg-fg/[0.025] p-0.5", className)}>
      {OPTIONS.map(([value, label, IconC]) => (
        <button key={value} type="button" role="radio" aria-checked={theme === value} aria-label={label} title={label} onClick={(e) => choose(value, e)}
          className={cx("relative grid h-7 flex-1 place-items-center rounded-[10px] transition-colors duration-150", theme === value ? "text-fg" : "text-fg-3 hover:text-fg-2")}>
          {theme === value && <motion.span layoutId={`theme-lens-${id}`} className="matte-lens absolute inset-0 rounded-[10px]" transition={{ duration: 0.3, ease: EASE_OUT }} />}
          <IconC className="relative size-3.5" />
        </button>
      ))}
    </div>
  );
}

/** One button that steps system → light → dark, for the collapsed sidebar. */
export function ThemeCycle({ className }: { className?: string }) {
  const [theme, choose] = useTheme();
  const i = OPTIONS.findIndex(([v]) => v === theme);
  const [, label, IconC] = OPTIONS[i];
  const next = OPTIONS[(i + 1) % OPTIONS.length];
  return (
    <button type="button" onClick={(e) => choose(next[0], e)} aria-label={`Theme: ${label}. Switch to ${next[1]}`} title={`Theme: ${label}`}
      className={cx("grid size-9 place-items-center rounded-xl text-fg-3 transition-colors hover:bg-fg/[0.06] hover:text-fg", className)}>
      <motion.span key={theme} initial={{ rotate: -90, scale: 0.6, opacity: 0 }} animate={{ rotate: 0, scale: 1, opacity: 1 }} transition={{ duration: 0.3, ease: EASE_OUT }}>
        <IconC className="size-4" />
      </motion.span>
    </button>
  );
}
