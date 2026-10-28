import type { ReactNode } from "react";

import type { Tone } from "@/lib/parse";

// The Figma components (docs/DESIGN.md), one to one.

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

const ICONS = {
  check: "M20 6 9 17l-5-5", x: "M18 6 6 18M6 6l12 12", clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  dashboard: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
  calendar: "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
  bulb: "M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01", activity: "M22 12h-4l-3 9L9 3l-3 9H2", refresh: "M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5",
} as const;
export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden className={cx("shrink-0", className)}>
      <path d={ICONS[name]} />
    </svg>
  );
}

const TONE: Record<Tone, string> = {
  ok: "bg-ok-bg text-ok", warn: "bg-warn-bg text-warn", error: "bg-err-bg text-err", info: "bg-info-bg text-info",
  neutral: "bg-raised text-fg-2",
};
const DOT: Record<Tone, string> = { ok: "bg-ok", warn: "bg-warn", error: "bg-err", info: "bg-info", neutral: "bg-fg-3" };

export function Dot({ tone, className }: { tone: Tone; className?: string }) {
  return <span aria-hidden className={cx("inline-block size-1.5 shrink-0 rounded-full", DOT[tone], className)} />;
}

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={cx("t-label inline-flex items-center gap-2 whitespace-nowrap rounded-full px-2 py-0.5", TONE[tone])}>
      <Dot tone={tone} />
      {children}
    </span>
  );
}

const BTN = {
  primary: "bg-primary text-on-primary hover:opacity-90",
  secondary: "bg-raised text-fg border border-line-strong hover:border-fg-3",
  danger: "bg-err-bg text-err hover:brightness-110",
  ghost: "text-fg-2 hover:text-fg hover:bg-raised",
};
export const buttonClass = (kind: keyof typeof BTN, extra?: string) =>
  cx("inline-flex h-9 items-center justify-center gap-2 rounded-md px-3.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50", BTN[kind], extra);

export function Card({ children, className, title, right, flush }: { children: ReactNode; className?: string; title?: ReactNode; right?: ReactNode; flush?: boolean }) {
  return (
    <section className={cx("rounded-lg border border-line bg-surface", flush ? "pt-4" : "p-5", className)}>
      {title && (
        <header className={cx("mb-4 flex items-center gap-3", flush && "mb-3 px-5")}>
          <h2 className="t-title">{title}</h2>
          <div className="ml-auto t-mono-sm text-fg-3">{right}</div>
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, sub, children }: { label: string; value: ReactNode; sub: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-surface p-4">
      <span className="t-label text-fg-3">{label}</span>
      <span className="t-metric truncate">{value}</span>
      {children}
      <span className="t-small text-fg-2">{sub}</span>
    </div>
  );
}

export function Meter({ used, max }: { used: number; max: number }) {
  const pct = Math.min(100, Math.round((used / max) * 100));
  const tone = used >= max ? "bg-err" : max - used < 10 ? "bg-warn" : "bg-info";
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-raised" role="meter" aria-valuenow={used} aria-valuemax={max} aria-label="model requests used">
      <div className={cx("h-full", tone)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ScoreTile({ label, score, reason }: { label: string; score: number; reason?: string }) {
  const pass = score >= 4;
  return (
    <div className={cx("flex min-w-0 flex-col gap-1 rounded-md border border-line p-3", pass ? "bg-raised" : "bg-warn-bg")}>
      <span className="t-label text-fg-3">{label}</span>
      <span className="flex items-baseline gap-0.5">
        <span className={cx("t-metric", pass ? "text-fg" : "text-warn")}>{score}</span>
        <span className="t-mono-sm text-fg-3">/5</span>
      </span>
      {reason && <span className="t-small line-clamp-3 text-fg-2">{reason}</span>}
    </div>
  );
}

export function GuardChip({ ok, label, title }: { ok: boolean; label: string; title?: string }) {
  return (
    <span title={title} className={cx("t-mono-sm inline-flex items-center gap-1 rounded-sm px-2 py-1", ok ? "bg-raised text-fg-2" : "bg-err-bg text-err")}>
      <Icon name={ok ? "check" : "x"} size={14} className={ok ? "text-ok" : "text-err"} />
      {label}
    </span>
  );
}

export function PageHeader({ title, sub, crumb, children }: { title: ReactNode; sub?: ReactNode; crumb?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        {crumb && <div className="t-mono-sm text-fg-3">{crumb}</div>}
        <h1 className="t-title-lg md:t-display">{title}</h1>
        {sub && <p className="t-small text-fg-2 md:text-sm">{sub}</p>}
      </div>
      {children && <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="t-small px-5 pb-5 text-fg-3">{children}</p>;
}
