"""``FakeBoard``: an in-memory board implementing ``BoardAdapter`` (constitution VII).

It keeps what the engagement layer relies on in the real board: revisions, updates with their own
ids (an update on the parent's side of a link keeps the parent's revision, as ADO, 015 T001),
``as_of`` equal to the latest change it has (015 research R-06), revision checks, and people
acting under their own identity (``as_user``). Tests switch it ``unreachable`` or make it refuse
the token. It passes the same contract suite as the ADO adapter (``tests/contract/board/``).
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from adlc.engagement.model import (
    BoardInfo,
    BoardItem,
    BoardType,
    BoardUpdate,
    ChangePage,
    FieldChange,
    Identity,
    ItemWrite,
)
from adlc.engagement.port import (
    BoardAuthFailed,
    BoardRefused,
    BoardUnreachable,
    ItemNotFound,
    RevisionConflict,
)

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
COMMENTS = "comments"  # the update key a comment records (the board's comment count)


def _time(tick: int) -> str:
    return (_EPOCH + timedelta(microseconds=tick)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class _Item:
    id: int
    type: str
    revisions: list[BoardItem] = field(default_factory=list)
    updates: list[BoardUpdate] = field(default_factory=list)
    changed_at: str = ""
    comments: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _State:
    types: Mapping[str, BoardType]
    areas: frozenset[str]
    identities: dict[str, str]
    state_field: str
    initial_states: Mapping[str, str]
    items: dict[int, _Item] = field(default_factory=dict)
    tick: int = 0
    unreachable: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)


class FakeBoard:
    def __init__(
        self,
        *,
        types: Mapping[str, BoardType],
        areas: frozenset[str],
        identities: Mapping[str, str],
        service_identity: str,
        state_field: str,
        initial_states: Mapping[str, str],
        _state: _State | None = None,
        _acting: str | None = None,
        _authorised: bool = True,
    ) -> None:
        self._state = _state or _State(
            types=dict(types),
            areas=frozenset(areas),
            identities={k.lower(): v for k, v in identities.items()},
            state_field=state_field,
            initial_states=dict(initial_states),
        )
        self.service_identity = service_identity.lower()
        self.acting = (_acting or service_identity).lower()
        self._authorised = _authorised

    # ------------------------------------------------------------------ test controls

    def as_user(self, unique_name: str) -> FakeBoard:
        """The same board, acting as another identity (a person using the board)."""
        return FakeBoard(
            types={},
            areas=frozenset(),
            identities={},
            service_identity=self.service_identity,
            state_field="",
            initial_states={},
            _state=self._state,
            _acting=unique_name,
        )

    def with_token_refused(self) -> FakeBoard:
        return FakeBoard(
            types={},
            areas=frozenset(),
            identities={},
            service_identity=self.service_identity,
            state_field="",
            initial_states={},
            _state=self._state,
            _acting=self.acting,
            _authorised=False,
        )

    @property
    def unreachable(self) -> bool:
        return self._state.unreachable

    @unreachable.setter
    def unreachable(self, value: bool) -> None:
        self._state.unreachable = value

    def item_ids(self) -> list[int]:
        return sorted(self._state.items)

    def comments(self, item_id: int) -> list[tuple[str, str]]:
        """(author, text) of every comment on the item, oldest first."""
        return list(self._item(item_id).comments)

    # ------------------------------------------------------------------ the port

    def check(self) -> BoardInfo:
        self._gate()
        return BoardInfo(types=dict(self._state.types), areas=self._state.areas)

    def create(
        self, item_type: str, fields: Mapping[str, Any], parent_id: int | None = None
    ) -> BoardItem:
        with self._state.lock:
            self._gate()
            kind = self._state.types.get(item_type)
            if kind is None:
                raise BoardRefused(f"unknown work item type {item_type!r}")
            values = {self._state.state_field: self._state.initial_states.get(item_type, "")}
            values.update({k: v for k, v in fields.items() if v not in (None, "")})
            self._validate(kind, values)
            if parent_id is not None:
                self._item(parent_id)
            item_id = len(self._state.items) + 1
            now = self._next()
            snapshot = BoardItem(item_id, 1, item_type, values, parent_id, self.acting)
            record = _Item(item_id, item_type, [snapshot], changed_at=now)
            record.updates.append(
                BoardUpdate(
                    item_id,
                    1,
                    1,
                    self.acting,
                    {k: FieldChange(None, v) for k, v in values.items()},
                    parent_added=parent_id,
                )
            )
            self._state.items[item_id] = record
            if parent_id is not None:
                parent = self._item(parent_id)
                parent.updates.append(
                    BoardUpdate(
                        parent_id,
                        len(parent.updates) + 1,
                        parent.revisions[-1].rev,
                        self.acting,
                    )
                )
            return snapshot

    def get(self, item_id: int) -> BoardItem:
        self._gate()
        return self._item(item_id).revisions[-1]

    def get_at(self, item_id: int, rev: int) -> BoardItem:
        self._gate()
        revisions = self._item(item_id).revisions
        if not 1 <= rev <= len(revisions):
            raise ItemNotFound(f"work item {item_id} has no revision {rev}")
        return revisions[rev - 1]

    def update(self, item_id: int, write: ItemWrite) -> BoardItem:
        with self._state.lock:
            self._gate()
            record = self._item(item_id)
            current = record.revisions[-1]
            if write.expected_rev is not None and write.expected_rev != current.rev:
                raise RevisionConflict(f"work item {item_id} is at revision {current.rev}")
            values = dict(current.fields)
            for name in write.clear:
                values.pop(name, None)
            for name, value in write.set.items():
                if value in (None, ""):
                    values.pop(name, None)
                else:
                    values[name] = value
            self._validate(self._state.types[record.type], values)
            changes = {
                name: FieldChange(current.fields.get(name), values.get(name))
                for name in set(current.fields) | set(values)
                if current.fields.get(name) != values.get(name)
            }
            if not changes:
                return current
            return self._revise(record, values, changes)

    def comment(self, item_id: int, text: str) -> None:
        with self._state.lock:
            self._gate()
            record = self._item(item_id)
            record.comments.append((self.acting, text))
            count = len(record.comments)
            current = record.revisions[-1]
            self._revise(record, dict(current.fields), {COMMENTS: FieldChange(count - 1, count)})

    def changed_since(self, watermark: str | None) -> ChangePage:
        with self._state.lock:
            self._gate()
            ordered = sorted(self._state.items.values(), key=lambda i: (i.changed_at, i.id))
            ids = tuple(i.id for i in ordered if watermark is None or i.changed_at >= watermark)
            latest = ordered[-1].changed_at if ordered else _time(self._state.tick)
            return ChangePage(ids, latest)

    def updates(self, item_id: int, after_update_id: int = 0) -> list[BoardUpdate]:
        self._gate()
        return [u for u in self._item(item_id).updates if u.update_id > after_update_id]

    def find_identity(self, unique_name: str) -> Identity | None:
        self._gate()
        name = unique_name.lower()
        display = self._state.identities.get(name)
        return None if display is None else Identity(name, display, f"fake-{name}")

    # ------------------------------------------------------------------ internals

    def _gate(self) -> None:
        if self._state.unreachable:
            raise BoardUnreachable("the board does not answer")
        if not self._authorised:
            raise BoardAuthFailed("the board refused the token")

    def _item(self, item_id: int) -> _Item:
        record = self._state.items.get(item_id)
        if record is None:
            raise ItemNotFound(f"no work item {item_id}")
        return record

    def _next(self) -> str:
        self._state.tick += 1
        return _time(self._state.tick)

    def _validate(self, kind: BoardType, values: Mapping[str, Any]) -> None:
        for name in values:
            if name not in kind.fields:
                raise BoardRefused(f"field {name} is not defined on {kind.name}")
        state = values.get(self._state.state_field)
        if state not in (None, "") and state not in kind.states:
            raise BoardRefused(f"state is not one of {kind.name}'s states")

    def _revise(
        self, record: _Item, values: dict[str, Any], changes: Mapping[str, FieldChange]
    ) -> BoardItem:
        current = record.revisions[-1]
        snapshot = replace(current, rev=current.rev + 1, fields=values, changed_by=self.acting)
        record.revisions.append(snapshot)
        record.updates.append(
            BoardUpdate(record.id, len(record.updates) + 1, snapshot.rev, self.acting, changes)
        )
        record.changed_at = self._next()
        return snapshot
