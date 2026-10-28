"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { fmtDay, fmtStamp, fmtTime, TZ_COOKIE, validTimeZone, zoneLabel } from "@/lib/time";

const TzCtx = createContext("UTC");
export const useTimeZone = () => useContext(TzCtx);

/** Starts with the zone the server rendered with (from the cookie), then switches to the device's own zone and
 * remembers it, so the next server render already matches. */
export function TimeZoneProvider({ initial, children }: { initial: string; children: ReactNode }) {
  const [tz, setTz] = useState(initial);
  useEffect(() => {
    const device = validTimeZone(Intl.DateTimeFormat().resolvedOptions().timeZone);
    if (device !== tz) setTz(device);
    document.cookie = `${TZ_COOKIE}=${encodeURIComponent(device)}; path=/; max-age=31536000; samesite=lax`;
  }, [tz]);
  return <TzCtx.Provider value={tz}>{children}</TzCtx.Provider>;
}

type Kind = "time" | "stamp" | "day";
const FORMAT: Record<Kind, (iso: string, tz: string) => string> = { time: fmtTime, stamp: fmtStamp, day: fmtDay };

/** An instant in the viewer's timezone. `zone` adds the offset label (GMT+8) once, where it helps. */
export function Time({ iso, kind = "stamp", zone, className }: { iso: string; kind?: Kind; zone?: boolean; className?: string }) {
  const tz = useTimeZone();
  return (
    <time dateTime={iso} className={className} title={`${fmtStamp(iso, tz)} ${zoneLabel(tz)}`} suppressHydrationWarning>
      {FORMAT[kind](iso, tz)}{zone ? ` ${zoneLabel(tz)}` : ""}
    </time>
  );
}
