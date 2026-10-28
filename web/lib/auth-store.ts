import { neon } from "@neondatabase/serverless";

import { afterFailure, type FailureRow, type Rule } from "./lockout";

// Failed sign-in counts for the lockout. The one table the web app writes; everything else is read-only here and
// written by the Python backend (harness/db_store.py).
let ready: Promise<unknown> | null = null;

function sql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  return neon(url);
}

/** Create the table once. Two requests can race on "create table if not exists" (Postgres then reports a duplicate
 * type), which still means the table exists; any other failure is forgotten so the next request tries again. */
function ensureTable() {
  ready ??= sql()`create table if not exists auth_failures (
    key text primary key, failures integer not null, window_start timestamptz not null)`.catch((e: { code?: string }) => {
    if (e?.code === "23505" || e?.code === "42P07") return;
    ready = null;
    throw e;
  });
  return ready;
}

export async function failures(key: string): Promise<FailureRow> {
  await ensureTable();
  const rows = await sql()`select failures, window_start from auth_failures where key = ${key}`;
  const r = rows[0];
  return r ? { failures: r.failures as number, window_start: new Date(r.window_start as string).toISOString() } : null;
}

export async function recordFailure(key: string, rule: Rule, now = new Date()): Promise<void> {
  const next = afterFailure(await failures(key), now, rule);
  await sql()`insert into auth_failures (key, failures, window_start) values (${key}, ${next.failures}, ${next.window_start})
    on conflict (key) do update set failures = excluded.failures, window_start = excluded.window_start`;
}

export async function clearFailures(key: string): Promise<void> {
  await ensureTable();
  await sql()`delete from auth_failures where key = ${key}`;
}
