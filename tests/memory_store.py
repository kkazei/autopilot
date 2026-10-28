"""An in-memory db_sync.Store, so the sync logic is tested without a database server."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any


class MemoryStore:
    def __init__(self) -> None:
        self.locked = False
        self.docs: dict[str, Any] = {}
        self.logs: dict[str, list[dict[str, Any]]] = {}
        self.runs: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
        self.put_run_calls = 0

    def try_lock(self) -> bool:
        if self.locked:
            return False
        self.locked = True
        return True

    def unlock(self) -> None:
        self.locked = False

    def get_doc(self, name: str) -> Any | None:
        return copy.deepcopy(self.docs.get(name))

    def put_doc(self, name: str, data: Any) -> None:
        self.docs[name] = json.loads(json.dumps(data))  # same round trip as jsonb

    def get_log(self, name: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.logs.get(name, []))

    def append_log(self, name: str, start: int, records: list[dict[str, Any]]) -> None:
        log = self.logs.setdefault(name, [])
        assert start == len(log), "append must start at the end, like the (log, seq) primary key"
        log.extend(json.loads(json.dumps(records)))

    def runs_since(self, since: datetime) -> dict[str, list[dict[str, Any]]]:
        return {rid: copy.deepcopy(ev) for rid, (started, ev) in self.runs.items() if started >= since}

    def put_run(self, run_id: str, started_at: datetime, events: list[dict[str, Any]]) -> None:
        self.put_run_calls += 1
        self.runs[run_id] = (started_at, json.loads(json.dumps(events)))
