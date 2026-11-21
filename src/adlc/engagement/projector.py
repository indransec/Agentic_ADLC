"""Outbound projection: the board follows the platform (US1; FR-005..FR-009; research R-03).

``scan`` finds use cases whose history grew since the cursor and marks them dirty; ``deliver_due``
projects each due one: compute its desired items, create missing ones (parents first) and write
the platform-written fields that differ, with the board's revision check. Delivery runs after the
platform's transactions commit and never inside one, so a slow or absent board never holds the
database. Failures are retried on the outbox's schedule and dead-lettered on the fifth.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Engine

from adlc.engagement import store
from adlc.engagement.desired import DesiredItem, desired, snapshot
from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.model import ItemWrite
from adlc.engagement.port import BoardAdapter, BoardError, ItemNotFound, RevisionConflict
from adlc.inbox.service import InboxService
from adlc.orchestration.interfaces import Clock
from adlc.orchestration.outbox import RETRY_DELAYS
from adlc.orchestration.service import Actor
from adlc.orchestration.tracing import span

log = logging.getLogger(__name__)
SYSTEM_ACTOR = Actor.system("board-projector")


class Projector:
    def __init__(
        self,
        engine: Engine,
        inbox: InboxService,
        board: BoardAdapter,
        mapping: TrackerMapping,
        evidence_url: str,
        clock: Clock,
        time_scale: float = 1.0,
    ) -> None:
        self.engine = engine
        self.inbox = inbox
        self.board = board
        self.mapping = mapping
        self.evidence_url = evidence_url
        self.clock = clock
        self.time_scale = time_scale

    # ------------------------------------------------------------------ loop

    def run_once(self) -> int:
        self.scan()
        return self.deliver_due()

    def scan(self) -> set[str]:
        with self.engine.begin() as conn:
            cursor = store.sync_state(conn).cursor
            found, moved = store.changed_usecases(conn, cursor)
            store.mark_dirty(conn, sorted(found), self.clock.now())
            store.set_cursor(conn, moved)
        return found

    def mark_dirty(self, usecase_id: str) -> None:
        with self.engine.begin() as conn:
            store.mark_dirty(conn, [usecase_id], self.clock.now())

    def deliver_due(self) -> int:
        with self.engine.connect() as conn:
            due = store.due_deliveries(conn, self.clock.now())
        delivered = 0
        for usecase in due:
            try:
                self.deliver(usecase)
            except BoardError as error:
                self._failed(usecase, f"{type(error).__name__}: {error}")
                continue
            except Exception as error:  # noqa: BLE001 - one use case never stops the others
                log.exception("board projection of %s failed", usecase)
                self._failed(usecase, type(error).__name__)
                continue
            with self.engine.begin() as conn:
                store.delivered(conn, usecase, self.clock.now())
            delivered += 1
        return delivered

    def requeue(self, usecase_id: str, actor: str) -> bool:
        with self.engine.begin() as conn:
            return store.requeue(conn, usecase_id, actor, self.clock.now())

    def delivery_summary(self) -> dict[str, Any]:
        with self.engine.connect() as conn:
            return store.delivery_summary(conn)

    # ------------------------------------------------------------------ one use case

    def items_for(self, usecase_id: str) -> list[DesiredItem]:
        with self.engine.connect() as conn:
            snap = snapshot(conn, self.inbox, usecase_id, SYSTEM_ACTOR)
        return [] if snap is None else desired(snap, self.mapping, self.evidence_url)

    def deliver(self, usecase_id: str) -> None:
        with span("board", "project", usecase_id=usecase_id):
            for item in self.items_for(usecase_id):
                self.write(item)

    def write(self, item: DesiredItem, *, force: bool = False) -> list[tuple[str, Any, Any]]:
        """Create or bring one item in step; returns (field, board value, platform value) for
        each platform-written field that differed (``force`` ignores the stored hash)."""
        with self.engine.connect() as conn:
            link = store.get_link(conn, item.kind, item.object_id)
            parent = None
            if item.parent is not None:
                parent_link = store.get_link(conn, *item.parent)
                parent = None if parent_link is None else parent_link.work_item_id
        if link is None:
            created = self.board.create(
                item.item_type, {**item.create_fields, **item.fields}, parent_id=parent
            )
            with self.engine.begin() as conn:
                store.put_link(
                    conn,
                    item.kind,
                    item.object_id,
                    created.id,
                    item.item_type,
                    self.clock.now(),
                    projected_hash=item.hash,
                    rev=created.rev,
                )
            log.info(
                "board item created kind=%s object=%s item=%s",
                item.kind,
                item.object_id,
                created.id,
            )
            return [(name, None, value) for name, value in item.fields.items()]
        if link.projected_hash == item.hash and not force:
            return []
        for attempt in (1, 2):
            try:
                current = self.board.get(link.work_item_id)
            except ItemNotFound:
                log.warning("board item %s of %s is gone", link.work_item_id, item.object_id)
                return []
            changes = {
                name: value
                for name, value in item.fields.items()
                if current.fields.get(name) != value
            }
            rev = current.rev
            if changes:
                try:
                    rev = self.board.update(
                        link.work_item_id, ItemWrite(set=changes, expected_rev=current.rev)
                    ).rev
                except RevisionConflict:
                    if attempt == 2:
                        raise
                    continue
            with self.engine.begin() as conn:
                store.set_projection(
                    conn, item.kind, item.object_id, item.hash, rev, self.clock.now()
                )
            return [(name, current.fields.get(name), value) for name, value in changes.items()]
        return []

    def _failed(self, usecase: str, error: str) -> None:
        with self.engine.begin() as conn:
            dead = store.delivery_failed(
                conn, usecase, error, self.clock.now(), RETRY_DELAYS, self.time_scale
            )
        if dead:
            log.error("board projection of %s dead-lettered: %s", usecase, error)
        else:
            log.warning("board projection of %s failed, will retry: %s", usecase, error)
