// Times in the viewer's own timezone. The zone comes from the browser (Intl), is sent to the server in the `tz`
// cookie so server-rendered pages match, and falls back to UTC until the browser has reported it.

export const TZ_COOKIE = "tz";
export const DEFAULT_TZ = "UTC";

/** A zone name only if Intl accepts it, so a tampered cookie can never throw during render. */
export function validTimeZone(tz: string | undefined | null): string {
  if (!tz) return DEFAULT_TZ;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz });
    return tz;
  } catch {
    return DEFAULT_TZ;
  }
}

const parts = (iso: string, tz: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", ...opts }).format(new Date(iso));

/** 14:05:24, for trace rows. */
export const fmtTime = (iso: string, tz: string) => parts(iso, tz, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** 14:17, for a time of day (the cron's daily slot). */
export const fmtHourMinute = (iso: string, tz: string) => parts(iso, tz, { hour: "2-digit", minute: "2-digit" });

/** Oct 26, 22:05, for headers and history. */
export const fmtStamp = (iso: string, tz: string) =>
  parts(iso, tz, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

/** "Wed 28": weekday then day, whatever order Intl would pick. */
function weekdayDay(date: Date, tz: string): string {
  const p = new Intl.DateTimeFormat("en-US", { timeZone: tz, weekday: "short", day: "2-digit" }).formatToParts(date);
  return `${p.find((x) => x.type === "weekday")?.value} ${p.find((x) => x.type === "day")?.value}`;
}

/** Wed 28, for "today" in the viewer's zone. */
export const fmtDay = (iso: string, tz: string) => weekdayDay(new Date(iso), tz);

/** GMT+8 / UTC: shown next to times so it is never ambiguous which clock they are on. */
export function zoneLabel(tz: string, at = new Date()): string {
  const name = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "shortOffset" }).formatToParts(at)
    .find((p) => p.type === "timeZoneName")?.value;
  return !name || name === "GMT" || name === "GMT+0" ? (name ? "UTC" : tz) : name;
}

/** Plan days are calendar dates (2026-10-28), not instants: they are never shifted between zones. */
export function dateLabel(isoDate: string): string {
  return weekdayDay(new Date(`${isoDate.slice(0, 10)}T12:00:00Z`), "UTC");
}
