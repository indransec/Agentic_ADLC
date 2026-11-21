"""The backlog tree (feature 018, FR-009, FR-010; research R-08).

One read of every item and every parent link; the tops are the board type's items without a
parent (under the chosen area), each with its descendants, children by id, at any depth. Items of
other types without a parent are not shown. A link cycle (impossible through the API) never loops.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ado_sim.db import Database
from ado_sim.pages.board import area_clause, choose_area
from ado_sim.process import BoardSettings, board_settings

PARENT = "System.LinkTypes.Hierarchy-Reverse"


@dataclass(frozen=True)
class TreeRow:
    id: int
    type: str
    title: str
    state: str
    children: tuple[TreeRow, ...] = ()


@dataclass(frozen=True)
class Backlog:
    settings: BoardSettings | None
    rows: tuple[TreeRow, ...] = ()
    area: str | None = None
    areas: tuple[str, ...] = ()
    notice: str | None = None


def tree(db: Database, area: str | None) -> Backlog:
    with db.read() as conn:
        settings = board_settings(conn)
        if settings is None:
            return Backlog(None, notice="The backlog needs the seed's board section (its type).")
        known, chosen, notice = choose_area(conn, area)
        items = {
            int(r["id"]): (str(r["type_name"]), json.loads(r["fields"]), str(r["state"]))
            for r in conn.execute("SELECT id, type_name, fields, state FROM work_item")
        }
        links = [
            (int(r[0]), int(r[1]))
            for r in conn.execute(
                "SELECT source_id, target_id FROM relation WHERE rel = ? ORDER BY source_id",
                (PARENT,),
            )
        ]
        sql = "SELECT id FROM work_item WHERE type_name = ?"
        params: list[object] = [settings.type]
        if chosen:
            clause, extra = area_clause(chosen)
            sql += " AND " + clause
            params += extra
        tops = [int(r[0]) for r in conn.execute(sql + " ORDER BY id", params)]
    children: dict[int, list[int]] = {}
    for child, parent in links:
        children.setdefault(parent, []).append(child)
    has_parent = {child for child, _ in links}

    def row(item_id: int, seen: frozenset[int]) -> TreeRow:
        kind, fields, state = items[item_id]
        below = tuple(
            row(child, seen | {child})
            for child in children.get(item_id, [])
            if child not in seen and child in items
        )
        return TreeRow(item_id, kind, str(fields.get("System.Title") or ""), state, below)

    rows = tuple(row(top, frozenset({top})) for top in tops if top not in has_parent)
    return Backlog(settings, rows, chosen, tuple(known), notice)
