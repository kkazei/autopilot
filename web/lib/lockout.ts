// Repeated wrong passwords lock sign-in for a while. Counted per username and per IP in Neon (lib/auth-store.ts),
// because Vercel functions share no memory. GitHub sign-in is unaffected, so a lockout never shuts the owner out.

export type Rule = { max: number; windowMs: number };
export type FailureRow = { failures: number; window_start: string } | null;

export const RULES = {
  user: { max: 5, windowMs: 15 * 60_000 },
  ip: { max: 10, windowMs: 15 * 60_000 },
} as const satisfies Record<string, Rule>;

export function lockState(row: FailureRow, now: Date, rule: Rule): { locked: boolean; retryAt: Date | null } {
  if (!row) return { locked: false, retryAt: null };
  const start = Date.parse(row.window_start);
  if (now.getTime() - start >= rule.windowMs) return { locked: false, retryAt: null };
  return row.failures >= rule.max ? { locked: true, retryAt: new Date(start + rule.windowMs) } : { locked: false, retryAt: null };
}

/** The row after one more failure: a new window once the old one has expired. */
export function afterFailure(row: FailureRow, now: Date, rule: Rule): { failures: number; window_start: string } {
  if (!row || now.getTime() - Date.parse(row.window_start) >= rule.windowMs) return { failures: 1, window_start: now.toISOString() };
  return { failures: row.failures + 1, window_start: row.window_start };
}
