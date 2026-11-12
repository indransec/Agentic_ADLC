"""The bridge's own append-only JSON Lines records (data-model.md, bridge volume): the call audit
(tool, run, outcome; never arguments or results) and the records other bridge servers keep."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adlc.tools.token import Claims


class Records:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.lock = threading.Lock()

    def add(self, name: str, **row: Any) -> dict[str, Any]:
        entry = {"at": datetime.now(UTC).isoformat(), **row}
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            with (self.folder / f"{name}.jsonl").open("a") as handle:
                handle.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
        return entry

    def read(self, name: str) -> list[dict[str, Any]]:
        path = self.folder / f"{name}.jsonl"
        if not path.exists():
            return []
        with self.lock:
            lines = path.read_text().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def audit(self, tool: str, claims: Claims | None, outcome: str) -> None:
        self.add(
            "calls",
            tool=tool,
            run_id=None if claims is None else claims.run_id,
            outcome=outcome,
        )
