"""Reconciliation: make the board match the platform, on demand (US7; FR-019, FR-020; D-13;
research R-08).

The projector's computation without its shortcut: for every use case, every desired item is read
from the board itself and each platform-written field that differs is written back (the platform
wins); missing items are created and linked, and items gone from the board are created again.
Only platform-written fields are compared, so a person's decision that inbound sync has not read
yet is left alone. The platform's own tables are only read. Each run is recorded with its
differences; board values are stored as hashes, never as text.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import Engine

from adlc.engagement import store
from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.port import BoardAdapter, BoardError, ItemNotFound
from adlc.engagement.projector import Projector
from adlc.orchestration.interfaces import Clock
from adlc.orchestration.service import Actor, NotAuthorised
from adlc.orchestration.tracing import span

log = logging.getLogger(__name__)


def _value_hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]


class Reconciler:
    def __init__(
        self,
        engine: Engine,
        projector: Projector,
        board: BoardAdapter,
        mapping: TrackerMapping,
        clock: Clock,
        coe_role: str | None,
    ) -> None:
        self.engine = engine
        self.projector = projector
        self.board = board
        self.mapping = mapping
        self.clock = clock
        self.coe_role = coe_role

    def reconcile(self, actor: Actor) -> dict[str, Any]:
        if not self.coe_role or self.coe_role not in actor.roles:
            raise NotAuthorised(f"reconciliation needs the role {self.coe_role}")
        started = self.clock.now()
        differences: list[dict[str, Any]] = []
        checked = created = 0
        outcome, error = "ok", None
        with span("board", "reconcile"):
            with self.engine.connect() as conn:
                usecases = store.all_usecases(conn)
            try:
                for usecase in usecases:
                    for item in self.projector.items_for(usecase):
                        checked += 1
                        with self.engine.connect() as conn:
                            link = store.get_link(conn, item.kind, item.object_id)
                        if link is not None:
                            try:
                                self.board.get(link.work_item_id)
                            except ItemNotFound:
                                with self.engine.begin() as conn:
                                    store.delete_link(conn, item.kind, item.object_id)
                                link = None
                        changes = self.projector.write(item, force=True)
                        if link is None:
                            created += 1
                            differences.append(
                                {
                                    "object_id": item.object_id,
                                    "work_item_id": None,
                                    "field": None,
                                    "board_value_hash": None,
                                    "platform_value": None,
                                    "action": "created",
                                }
                            )
                            continue
                        differences += [
                            {
                                "object_id": item.object_id,
                                "work_item_id": link.work_item_id,
                                "field": name,
                                "board_value_hash": _value_hash(board_value),
                                "platform_value": platform_value,
                                "action": "corrected",
                            }
                            for name, board_value, platform_value in changes
                        ]
            except BoardError as failure:
                outcome, error = "failed", f"{type(failure).__name__}: {failure}"
        with self.engine.begin() as conn:
            report_id = store.insert_reconciliation(
                conn,
                actor.account_name,
                started,
                self.clock.now(),
                outcome,
                checked,
                created,
                differences,
                error,
            )
        log.info(
            "board reconciliation %s by %s: %s, %d items, %d differences",
            report_id,
            actor.account_name,
            outcome,
            checked,
            len(differences),
        )
        report = self.report(report_id)
        assert report is not None  # noqa: S101 - just written
        return report

    def report(self, report_id: int | None) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            return store.reconciliation(conn, report_id)
