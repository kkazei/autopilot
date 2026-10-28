"use client";

import { useLive } from "./live";
import { useTimeZone } from "./time";
import { fmtHourMinute, zoneLabel } from "@/lib/time";
import { Dot } from "./ui";
import type { Tone } from "@/lib/parse";

export function SystemLights({ compact }: { compact?: boolean }) {
  const { live, dbOk, waking } = useLive();
  const tz = useTimeZone();
  // The cron runs daily at 06:17 UTC (.github/workflows/run.yml); shown on the viewer's clock.
  const cron = fmtHourMinute(`${new Date().toISOString().slice(0, 10)}T06:17:00Z`, tz);
  const backend: [Tone, string] = !live ? ["neutral", "checking"] : live.backend === "up" ? ["ok", "render"] : waking ? ["warn", "waking…"] : ["error", "asleep"];
  if (compact) {
    return (
      <span className="t-mono-sm inline-flex items-center gap-1.5 text-fg-2">
        <Dot tone={backend[0]} /> {backend[0] === "ok" ? "live" : backend[1]}
      </span>
    );
  }
  const rows: [string, Tone, string][] = [
    ["backend", ...backend],
    ["database", dbOk ? "ok" : "error", dbOk ? "neon" : "error"],
    ["cron", "ok", `${cron} ${zoneLabel(tz).toLowerCase()}`],
  ];
  return (
    <ul className="flex flex-col gap-2">
      {rows.map(([k, tone, v]) => (
        <li key={k} className="t-mono-sm flex items-center gap-2">
          <Dot tone={tone} />
          <span className="text-fg-2">{k}</span>
          <span className="ml-auto text-fg-3">{v}</span>
        </li>
      ))}
    </ul>
  );
}
