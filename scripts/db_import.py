"""Copy data/ into Postgres once, so the hosted app starts from the same history as the local one.

    python -m scripts.db_import
    python -m scripts.db_import --data-dir path/to/data

Safe to repeat: traces are upserted, and a log only gains the records the database does not have yet. A log that
no longer starts with what the database holds is refused, never overwritten.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from harness import trace
from harness.db_store import PostgresStore
from harness.db_sync import Store, StoreBusy, SyncError, push
from harness.env import load_dotenv
from scripts.db_run import EXIT_BUSY
from scripts.run_outer import DEFAULT_ENV_FILE


def main(argv: Sequence[str] | None = None, *, store: Store | None = None) -> int:
    p = argparse.ArgumentParser(prog="db_import", description=__doc__.split("\n")[0])
    p.add_argument("--data-dir", type=Path, default=None, help="default: data/ (or AUTOPILOT_DATA_DIR)")
    args = p.parse_args(argv)
    data_dir = args.data_dir or trace.data_dir()
    if store is None:
        load_dotenv(DEFAULT_ENV_FILE)
        store = PostgresStore.from_env()
    if not store.try_lock():
        print(f"refused: {StoreBusy.__doc__}", flush=True)
        return EXIT_BUSY
    try:
        report = push(store, data_dir)
    except SyncError as e:
        print(f"error: {e}", flush=True)
        return 1
    finally:
        store.unlock()
    appended = ", ".join(f"{name} +{n}" for name, n in report.appended.items())
    print(f"imported: {report.runs} traces; {appended}; docs updated: {', '.join(report.docs) or 'none'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
