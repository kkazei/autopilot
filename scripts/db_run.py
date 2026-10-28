"""Run the outer loop against Postgres instead of data/: pull the state, run, push it back.

    python -m scripts.db_run --measure-only
    python -m scripts.db_run --dry-run --no-approve

Every argument goes to scripts.run_outer unchanged. Needs DATABASE_URL (the direct, non-pooled URL).
Exit codes: run_outer's, plus 6 when another hosted run holds the lock and 7 when the result could not be saved.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from harness.db_store import PostgresStore
from harness.db_sync import Store, StoreBusy, SyncError, hosted_data_dir
from harness.env import load_dotenv
from scripts import run_outer

EXIT_BUSY = 6
EXIT_NOT_SAVED = 7


def main(argv: Sequence[str] | None = None, *, store: Store | None = None,
         runner: Callable[[list[str]], int] = run_outer.main) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if store is None:
        load_dotenv(run_outer.DEFAULT_ENV_FILE)
        store = PostgresStore.from_env()
    with tempfile.TemporaryDirectory(prefix="autopilot-", ignore_cleanup_errors=True) as tmp:
        try:
            with hosted_data_dir(store, Path(tmp)):
                return runner(args)
        except StoreBusy as e:
            print(f"refused: {e}", flush=True)
            return EXIT_BUSY
        except SyncError as e:
            print(f"error: the run finished but its state was not fully saved: {e}", flush=True)
            return EXIT_NOT_SAVED


if __name__ == "__main__":
    sys.exit(main())
