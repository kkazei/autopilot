// Relative times and ids. Clock times are formatted in the viewer's zone by components/time.tsx (lib/time.ts).

export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 90) return `${s}s ago`;
  if (s < 90 * 60) return `${Math.round(s / 60)}m ago`;
  if (s < 36 * 3600) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

/** "in 23m": the time left until `iso`, in the same units as ago(). */
export function until(iso: string, now = Date.now()): string {
  return `in ${ago(new Date(now - (Date.parse(iso) - now)).toISOString(), now).replace(" ago", "")}`;
}

export const shortRun = (runId: string) => `…${runId.slice(-13)}`;
