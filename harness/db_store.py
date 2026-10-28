"""The Postgres side of db_sync: three tables, created on first connect, and one advisory lock.

Values are jsonb rather than text so the web app can query plans, posts and traces directly. Connect with the
direct (non-pooled) URL: an advisory lock belongs to one server session, and a pooler in transaction mode would
hand that session to another client mid-run.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

URL_ENV = "DATABASE_URL"
CONNECT_TIMEOUT_S = 30  # Neon wakes a suspended database on connect, which can take a few seconds
LOCK_KEY = 0x4175746F  # "Auto": one lock for every hosted run, cron and web alike

SCHEMA = """
create table if not exists docs (
    name text primary key,
    data jsonb not null,
    updated_at timestamptz not null default now()
);
create table if not exists log_records (
    log text not null,
    seq integer not null,
    data jsonb not null,
    created_at timestamptz not null default now(),
    primary key (log, seq)
);
create table if not exists runs (
    run_id text primary key,
    started_at timestamptz not null,
    updated_at timestamptz not null default now(),
    events jsonb not null
);
create index if not exists runs_started_at on runs (started_at desc);
"""


class PostgresStore:
    """One autocommit connection; psycopg serializes its use, so the live pusher thread can share it."""

    def __init__(self, url: str) -> None:
        import psycopg  # imported here so the CLI and the tests run without the driver installed

        self._conn = psycopg.connect(url, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S)
        self._conn.execute(SCHEMA)

    @classmethod
    def from_env(cls) -> PostgresStore:
        url = os.environ.get(URL_ENV)
        if not url:
            raise RuntimeError(f"{URL_ENV} is not set")
        return cls(url)

    def close(self) -> None:
        self._conn.close()

    def try_lock(self) -> bool:
        row = self._conn.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()
        return bool(row and row[0])

    def unlock(self) -> None:
        self._conn.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))

    def get_doc(self, name: str) -> Any | None:
        row = self._conn.execute("select data from docs where name = %s", (name,)).fetchone()
        return row[0] if row else None

    def put_doc(self, name: str, data: Any) -> None:
        from psycopg.types.json import Jsonb

        self._conn.execute(
            "insert into docs (name, data) values (%s, %s) "
            "on conflict (name) do update set data = excluded.data, updated_at = now()",
            (name, Jsonb(data)))

    def get_log(self, name: str) -> list[dict[str, Any]]:
        rows = self._conn.execute("select data from log_records where log = %s order by seq", (name,)).fetchall()
        return [r[0] for r in rows]

    def append_log(self, name: str, start: int, records: list[dict[str, Any]]) -> None:
        """One transaction; the (log, seq) key makes a concurrent append fail instead of interleaving."""
        from psycopg.types.json import Jsonb

        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.executemany("insert into log_records (log, seq, data) values (%s, %s, %s)",
                            [(name, start + i, Jsonb(r)) for i, r in enumerate(records)])

    def runs_since(self, since: datetime) -> dict[str, list[dict[str, Any]]]:
        rows = self._conn.execute("select run_id, events from runs where started_at >= %s", (since,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def put_run(self, run_id: str, started_at: datetime, events: list[dict[str, Any]]) -> None:
        from psycopg.types.json import Jsonb

        self._conn.execute(
            "insert into runs (run_id, started_at, events) values (%s, %s, %s) "
            "on conflict (run_id) do update set events = excluded.events, updated_at = now()",
            (run_id, started_at, Jsonb(events)))
