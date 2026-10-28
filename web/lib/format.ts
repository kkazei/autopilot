// Times are shown in UTC, like the harness and the trace, so the server and the browser always agree.
const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const utcTime = (iso: string) => new Date(iso).toISOString().slice(11, 19);
export const utcDay = (isoDate: string) => {
  const d = new Date(isoDate.length === 10 ? `${isoDate}T00:00:00Z` : isoDate);
  return `${WEEKDAY[d.getUTCDay()]} ${String(d.getUTCDate()).padStart(2, "0")}`;
};
export const utcStamp = (iso: string) => {
  const d = new Date(iso);
  return `${d.toLocaleString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })}, ${d.toISOString().slice(11, 16)} UTC`;
};
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 90) return `${s}s ago`;
  if (s < 90 * 60) return `${Math.round(s / 60)}m ago`;
  if (s < 36 * 3600) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
export const shortRun = (runId: string) => `…${runId.slice(-13)}`;
/** "in 23m": the time left until `iso`, in the same units as ago(). */
export function until(iso: string, now = Date.now()): string {
  return `in ${ago(new Date(now - (Date.parse(iso) - now)).toISOString(), now).replace(" ago", "")}`;
}
