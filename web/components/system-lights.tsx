"use client";

import { useLive } from "./live";
import { Dot } from "./ui";
import type { Tone } from "@/lib/parse";

export function SystemLights({ compact }: { compact?: boolean }) {
  const { live, dbOk, waking } = useLive();
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
    ["cron", "ok", "06:17 utc"],
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
