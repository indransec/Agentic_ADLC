"""Work items: create, read, update, history and links (US1, US2, US4).

Every change runs in one write transaction: the item's new values, one revision row (the full
item) and one update row (what changed, who, when). A link added or removed from one item also
records an update on the other item, with its revision unchanged, as ADO does.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ado_sim.db import Database, format_time, later_than, utc_now
from ado_sim.errors import invalid, not_found, work_item_not_found
from ado_sim.patch import RELATION_TYPES, Relation, apply_patch
from ado_sim.process import (
    Identity,
    TypeInfo,
    all_fields,
    area_paths,
    identity_by_name,
    project_info,
    type_info,
)

MAX_IDS = 200
LATEST_REVISED_DATE = "9999-01-01T00:00:00Z"
HIERARCHY_CHILD = "System.LinkTypes.Hierarchy-Forward"
HIERARCHY_PARENT = "System.LinkTypes.Hierarchy-Reverse"


@dataclass(frozen=True)
class ItemView:
    id: int
    rev: int
    fields: dict[str, Any]
    relations: list[Relation]


@dataclass(frozen=True)
class UpdateView:
    id: int
    work_item_id: int
    rev: int
    revised_by: dict[str, Any]
    revised_date: str
    fields: dict[str, Any]
    relations: dict[str, Any]


class _ValidateOnly(Exception):  # noqa: N818 - control flow, never escapes this module
    def __init__(self, view: ItemView):
        self.view = view


def normalise_as_of(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise invalid(f"asOf '{value}' is not an ISO 8601 date and time.") from error
    return format_time(moment if moment.tzinfo else moment.replace(tzinfo=UTC))


class WorkItemStore:
    def __init__(self, db: Database, clock: Callable[[], str] = utc_now):
        self.db = db
        self.clock = clock

    # ----------------------------------------------------------------- writes

    def create(
        self,
        type_name: str,
        operations: Any,
        by: Identity,
        *,
        validate_only: bool = False,
    ) -> ItemView:
        try:
            with self.db.write() as conn:
                kind = self._type(conn, type_name)
                project = project_info(conn)
                assert project is not None  # noqa: S101 - the app refuses requests before seeding
                start = {
                    "System.TeamProject": project.project,
                    "System.WorkItemType": kind.name,
                    "System.State": kind.state_names[0],
                    "System.Reason": "New",
                    "System.AreaPath": project.project,
                }
                result = apply_patch(
                    operations,
                    kind=kind,
                    fields=start,
                    relations=[],
                    rev=None,
                    area_paths=area_paths(conn),
                    resolve_identity=lambda name: identity_by_name(conn, name),
                )
                if "System.Title" not in result.fields:
                    raise invalid(
                        "TF401320: Rule Error for field Title. Error code: Required, InvalidEmpty.",
                        "RuleValidationException",
                    )
                now = self._stamp(conn)
                cursor = conn.execute(
                    "INSERT INTO work_item (type_name, rev, fields, changed_date, state, area_path)"
                    " VALUES (?, 1, '{}', ?, '', '')",
                    (kind.name, now),
                )
                item_id = int(cursor.lastrowid or 0)
                fields = dict(result.fields)
                fields.update(
                    {
                        "System.Id": item_id,
                        "System.Rev": 1,
                        "System.CreatedBy": by.reference(),
                        "System.CreatedDate": now,
                        "System.ChangedBy": by.reference(),
                        "System.ChangedDate": now,
                        "System.CommentCount": 0,
                    }
                )
                self._apply_links(conn, item_id, result.added, [], by, now)
                self._save(
                    conn,
                    item_id,
                    1,
                    fields,
                    by,
                    now,
                    bearing_fields=_creation(fields),
                    added=result.added,
                    removed=[],
                )
                view = self._current(conn, item_id)
                if validate_only:
                    raise _ValidateOnly(view)
                return view
        except _ValidateOnly as preview:
            return preview.view

    def update(
        self,
        item_id: int,
        operations: Any,
        by: Identity,
        *,
        validate_only: bool = False,
    ) -> ItemView:
        try:
            with self.db.write() as conn:
                row = self._row(conn, item_id)
                kind = self._type(conn, row["type_name"])
                current = json.loads(row["fields"])
                relations = self._relations(conn, item_id)
                result = apply_patch(
                    operations,
                    kind=kind,
                    fields=current,
                    relations=relations,
                    rev=int(row["rev"]),
                    area_paths=area_paths(conn),
                    resolve_identity=lambda name: identity_by_name(conn, name),
                )
                if not result.changed:
                    return self._current(conn, item_id)
                when = self._stamp(conn)
                self._apply_links(conn, item_id, result.added, result.removed, by, when)
                self.commit_change(
                    conn,
                    row,
                    result.fields,
                    by,
                    added=result.added,
                    removed=result.removed,
                    when=when,
                )
                view = self._current(conn, item_id)
                if validate_only:
                    raise _ValidateOnly(view)
                return view
        except _ValidateOnly as preview:
            return preview.view

    def _stamp(self, conn: sqlite3.Connection) -> str:
        """The time of a new change: the clock, but always after the latest change to any item.

        Writes are serialised (``BEGIN IMMEDIATE``), so changed dates increase strictly in commit
        order across the whole database; a query's ``asOf`` (the latest changed date in its
        snapshot) is then a complete "changed since" bound for the next poll (research R-06).
        """
        latest = conn.execute("SELECT MAX(changed_date) FROM work_item").fetchone()[0]
        return later_than(latest, self.clock())

    def commit_change(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        new_fields: dict[str, Any],
        by: Identity,
        *,
        added: Sequence[Relation] = (),
        removed: Sequence[Relation] = (),
        transient: dict[str, Any] | None = None,
        when: str | None = None,
    ) -> str:
        """Record one revision of an item: new values, revision row, update row.

        ``transient`` values (such as ``System.History`` for a comment) appear in this
        revision and its update but are not kept as current values. Returns the change time.
        """
        item_id = int(row["id"])
        old_fields = json.loads(row["fields"])
        rev = int(row["rev"]) + 1
        when = when or self._stamp(conn)
        fields = dict(new_fields)
        fields.update(
            {"System.Rev": rev, "System.ChangedBy": by.reference(), "System.ChangedDate": when}
        )
        changes = _differences(old_fields, fields)
        for ref, value in (transient or {}).items():
            changes[ref] = {"newValue": value}
        self._save(
            conn,
            item_id,
            rev,
            fields,
            by,
            when,
            bearing_fields=changes,
            added=list(added),
            removed=list(removed),
            transient=transient,
        )
        return when

    def _save(
        self,
        conn: sqlite3.Connection,
        item_id: int,
        rev: int,
        fields: dict[str, Any],
        by: Identity,
        when: str,
        *,
        bearing_fields: dict[str, Any],
        added: Sequence[Relation],
        removed: Sequence[Relation],
        transient: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            "UPDATE work_item SET rev = ?, fields = ?, changed_date = ?, state = ?, area_path = ?,"
            " comment_count = ? WHERE id = ?",
            (
                rev,
                json.dumps(fields),
                when,
                fields["System.State"],
                fields["System.AreaPath"],
                int(fields.get("System.CommentCount", 0)),
                item_id,
            ),
        )
        snapshot = dict(fields)
        snapshot.update(transient or {})
        conn.execute(
            "INSERT INTO revision (work_item_id, rev, fields, relations) VALUES (?, ?, ?, ?)",
            (
                item_id,
                rev,
                json.dumps(snapshot),
                json.dumps([r.stored() for r in self._relations(conn, item_id)]),
            ),
        )
        self._record_update(
            conn, item_id, rev, True, by, when, bearing_fields, _relation_changes(added, removed)
        )

    def _record_update(
        self,
        conn: sqlite3.Connection,
        item_id: int,
        rev: int,
        bearing: bool,
        by: Identity,
        when: str,
        fields: dict[str, Any],
        relations: dict[str, Any],
    ) -> None:
        next_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM work_item_update WHERE work_item_id = ?",
            (item_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO work_item_update (work_item_id, id, rev, revision_bearing, revised_by,"
            " change_date, fields, relations) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item_id,
                next_id,
                rev,
                int(bearing),
                by.id,
                when,
                json.dumps(fields),
                json.dumps(relations),
            ),
        )

    # ------------------------------------------------------------------ links

    def _apply_links(
        self,
        conn: sqlite3.Connection,
        source_id: int,
        added: Sequence[Relation],
        removed: Sequence[Relation],
        by: Identity,
        when: str,
    ) -> None:
        """Write link changes in both directions and record them on the other items."""
        other_side: dict[int, tuple[list[Relation], list[Relation]]] = {}
        for relation in removed:
            reverse = Relation(_reverse(relation.rel), source_id, relation.attributes)
            conn.execute(
                "DELETE FROM relation WHERE (source_id = ? AND target_id = ? AND rel = ?)"
                " OR (source_id = ? AND target_id = ? AND rel = ?)",
                (
                    source_id,
                    relation.target_id,
                    relation.rel,
                    relation.target_id,
                    source_id,
                    reverse.rel,
                ),
            )
            other_side.setdefault(relation.target_id, ([], []))[1].append(reverse)
        for relation in added:
            target = relation.target_id
            if target == source_id:
                raise invalid("A work item cannot be linked to itself.", "WorkItemLinkException")
            if conn.execute("SELECT 1 FROM work_item WHERE id = ?", (target,)).fetchone() is None:
                raise invalid(
                    f"The link target, work item {target}, does not exist.", "WorkItemLinkException"
                )
            if relation.rel == HIERARCHY_PARENT:
                self._check_hierarchy(conn, parent=target, child=source_id)
            elif relation.rel == HIERARCHY_CHILD:
                self._check_hierarchy(conn, parent=source_id, child=target)
            reverse = Relation(_reverse(relation.rel), source_id, relation.attributes)
            for left, right in ((source_id, relation), (target, reverse)):
                conn.execute(
                    "INSERT INTO relation (source_id, target_id, rel, attributes)"
                    " VALUES (?, ?, ?, ?)",
                    (left, right.target_id, right.rel, json.dumps(right.attributes)),
                )
            other_side.setdefault(target, ([], []))[0].append(reverse)
        for target, (target_added, target_removed) in sorted(other_side.items()):
            row = self._row(conn, target)
            self._record_update(
                conn,
                target,
                int(row["rev"]),
                False,
                by,
                when,
                {},
                _relation_changes(target_added, target_removed),
            )

    def _check_hierarchy(self, conn: sqlite3.Connection, *, parent: int, child: int) -> None:
        if self._parent(conn, child) is not None:
            raise invalid(
                f"Work item {child} already has a parent; a work item has at most one parent.",
                "WorkItemLinkException",
            )
        ancestor: int | None = parent
        seen: set[int] = set()
        while ancestor is not None and ancestor not in seen:
            if ancestor == child:
                raise invalid(
                    f"Linking {child} under {parent} would create a cycle in the hierarchy.",
                    "WorkItemLinkException",
                )
            seen.add(ancestor)
            ancestor = self._parent(conn, ancestor)

    @staticmethod
    def _parent(conn: sqlite3.Connection, item_id: int) -> int | None:
        row = conn.execute(
            "SELECT target_id FROM relation WHERE source_id = ? AND rel = ?",
            (item_id, HIERARCHY_PARENT),
        ).fetchone()
        return int(row["target_id"]) if row else None

    # ------------------------------------------------------------------ reads

    def get(self, item_id: int, as_of: str | None = None) -> ItemView:
        with self.db.read() as conn:
            if as_of is None:
                return self._current(conn, item_id)
            view = self._as_of(conn, item_id, as_of)
            if view is None:
                raise work_item_not_found(item_id)
            return view

    def get_many(
        self, ids: Sequence[int], *, as_of: str | None = None, omit_missing: bool = False
    ) -> list[ItemView]:
        if len(ids) > MAX_IDS:
            raise invalid(f"At most {MAX_IDS} work items can be read in one request.")
        views: list[ItemView] = []
        with self.db.read() as conn:
            for item_id in ids:
                view = (
                    self._as_of(conn, item_id, as_of)
                    if as_of
                    else (self._current(conn, item_id) if self._exists(conn, item_id) else None)
                )
                if view is None:
                    if omit_missing:
                        continue
                    raise work_item_not_found(item_id)
                views.append(view)
        return views

    def updates(self, item_id: int) -> list[UpdateView]:
        with self.db.read() as conn:
            row = self._row(conn, item_id)
            current_rev = int(row["rev"])
            next_dates = {
                int(r["rev"]): json.loads(r["fields"])["System.ChangedDate"]
                for r in conn.execute(
                    "SELECT rev, fields FROM revision WHERE work_item_id = ?", (item_id,)
                )
            }
            people: dict[str, dict[str, Any]] = {}
            views: list[UpdateView] = []
            for update in conn.execute(
                "SELECT * FROM work_item_update WHERE work_item_id = ? ORDER BY id", (item_id,)
            ):
                rev = int(update["rev"])
                if update["revision_bearing"]:
                    revised = LATEST_REVISED_DATE if rev == current_rev else next_dates[rev + 1]
                else:
                    revised = update["change_date"]
                by = update["revised_by"]
                if by not in people:
                    person = conn.execute("SELECT * FROM identity WHERE id = ?", (by,)).fetchone()
                    people[by] = {
                        "displayName": person["display_name"],
                        "id": person["id"],
                        "uniqueName": person["unique_name"],
                    }
                views.append(
                    UpdateView(
                        id=int(update["id"]),
                        work_item_id=item_id,
                        rev=rev,
                        revised_by=people[by],
                        revised_date=revised,
                        fields=json.loads(update["fields"]),
                        relations=json.loads(update["relations"]),
                    )
                )
            return views

    def revisions(self, item_id: int) -> list[ItemView]:
        with self.db.read() as conn:
            self._row(conn, item_id)
            return [
                _revision_view(item_id, r)
                for r in conn.execute(
                    "SELECT * FROM revision WHERE work_item_id = ? ORDER BY rev", (item_id,)
                )
            ]

    def revision(self, item_id: int, rev: int) -> ItemView:
        with self.db.read() as conn:
            self._row(conn, item_id)
            row = conn.execute(
                "SELECT * FROM revision WHERE work_item_id = ? AND rev = ?", (item_id, rev)
            ).fetchone()
            if row is None:
                raise not_found(f"Work item {item_id} has no revision {rev}.")
            return _revision_view(item_id, row)

    def known_fields(self) -> set[str]:
        with self.db.read() as conn:
            return {f.reference_name for f in all_fields(conn).values()}

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _type(conn: sqlite3.Connection, name: str) -> TypeInfo:
        kind = type_info(conn, name)
        if kind is None:
            raise not_found(
                f"TF201083: Work item type {name} does not exist.", "WorkItemTypeNotFoundException"
            )
        return kind

    @staticmethod
    def _exists(conn: sqlite3.Connection, item_id: int) -> bool:
        return (
            conn.execute("SELECT 1 FROM work_item WHERE id = ?", (item_id,)).fetchone() is not None
        )

    @staticmethod
    def _row(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM work_item WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise work_item_not_found(item_id)
        return row  # type: ignore[no-any-return]

    @staticmethod
    def _relations(conn: sqlite3.Connection, item_id: int) -> list[Relation]:
        return [
            Relation(r["rel"], int(r["target_id"]), json.loads(r["attributes"]))
            for r in conn.execute(
                "SELECT * FROM relation WHERE source_id = ? ORDER BY rowid", (item_id,)
            )
        ]

    def _current(self, conn: sqlite3.Connection, item_id: int) -> ItemView:
        row = self._row(conn, item_id)
        return ItemView(
            item_id, int(row["rev"]), json.loads(row["fields"]), self._relations(conn, item_id)
        )

    @staticmethod
    def _as_of(conn: sqlite3.Connection, item_id: int, as_of: str) -> ItemView | None:
        moment = normalise_as_of(as_of)
        row = conn.execute(
            "SELECT * FROM revision WHERE work_item_id = ?"
            " AND json_extract(fields, '$.\"System.ChangedDate\"') <= ? ORDER BY rev DESC LIMIT 1",
            (item_id, moment),
        ).fetchone()
        return _revision_view(item_id, row) if row else None


def _revision_view(item_id: int, row: sqlite3.Row) -> ItemView:
    return ItemView(
        item_id,
        int(row["rev"]),
        json.loads(row["fields"]),
        [Relation.from_stored(r) for r in json.loads(row["relations"])],
    )


def _reverse(rel: str) -> str:
    return RELATION_TYPES[rel][0]


def _creation(fields: dict[str, Any]) -> dict[str, Any]:
    return {ref: {"newValue": value} for ref, value in sorted(fields.items())}


def _differences(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for ref in sorted(set(old) | set(new)):
        if old.get(ref) != new.get(ref):
            entry: dict[str, Any] = {}
            if ref in old:
                entry["oldValue"] = old[ref]
            if ref in new:
                entry["newValue"] = new[ref]
            changes[ref] = entry
    return changes


def _relation_changes(added: Sequence[Relation], removed: Sequence[Relation]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if added:
        changes["added"] = [r.stored() for r in added]
    if removed:
        changes["removed"] = [r.stored() for r in removed]
    return changes
