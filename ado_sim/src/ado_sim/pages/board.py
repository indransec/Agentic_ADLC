"""The board's columns and cards (017 FR-005, FR-006, FR-009; research R-06).

One read: the board type's states in process order (seed board settings), and every item of that
type under the chosen area with its title, the configured card fields and its last changer.
Items in a state the type no longer lists go to an "other" column at the end. Values are returned
as text; the templates escape them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ado_sim.db import Database
from ado_sim.process import BoardSettings, board_settings


@dataclass(frozen=True)
class Card:
    id: int
    title: str
    fields: tuple[tuple[str, str], ...]  # (field name, value) for the configured card fields
    changed_by: str


@dataclass(frozen=True)
class Column:
    state: str
    collapsed: bool
    cards: tuple[Card, ...]
    other: bool = False

    @property
    def count(self) -> int:
        return len(self.cards)


@dataclass(frozen=True)
class Board:
    settings: BoardSettings | None
    columns: tuple[Column, ...] = ()
    area: str | None = None
    areas: tuple[str, ...] = ()
    notice: str | None = None
    names: dict[str, str] = field(default_factory=dict)


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("displayName") or value.get("uniqueName") or "")
    return "" if value is None else str(value)


def columns(db: Database, area: str | None) -> Board:
    with db.read() as conn:
        settings = board_settings(conn)
        if settings is None:
            return Board(
                None, notice="The board is not configured (the seed has no board section)."
            )
        known = [str(r[0]) for r in conn.execute("SELECT path FROM area_node ORDER BY path")]
        chosen = next((a for a in known if area and a.lower() == area.lower()), None)
        notice = (
            None
            if area is None or chosen
            else f"There is no area path '{area}'; showing every area."
        )
        states = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM work_item_type_state WHERE type_name = ? ORDER BY ordinal",
                (settings.type,),
            )
        ]
        names = (
            {
                r[0]: r[1]
                for r in conn.execute(
                    "SELECT reference_name, name FROM field WHERE reference_name IN ("  # noqa: S608
                    + ",".join("?" * len(settings.card_fields))
                    + ")",
                    settings.card_fields,
                )
            }
            if settings.card_fields
            else {}
        )
        sql = "SELECT id, state, fields FROM work_item WHERE type_name = ?"
        params: list[Any] = [settings.type]
        if chosen:
            sql += " AND (area_path = ? COLLATE NOCASE OR area_path LIKE ? ESCAPE '!')"
            escaped = chosen.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            params += [chosen, escaped + "\\%"]
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    grouped: dict[str, list[Card]] = {}
    for row in rows:
        values = json.loads(row["fields"])
        card_fields = tuple(
            (names.get(ref, ref), _text(values.get(ref)))
            for ref in settings.card_fields
            if values.get(ref) not in (None, "")
        )
        grouped.setdefault(row["state"], []).append(
            Card(
                int(row["id"]),
                _text(values.get("System.Title")),
                card_fields,
                _text(values.get("System.ChangedBy")),
            )
        )
    collapsed = {s.lower() for s in settings.collapsed_states}
    result = [
        Column(state, state.lower() in collapsed, tuple(grouped.pop(state, []))) for state in states
    ]
    result += [
        Column(state, False, tuple(cards), other=True) for state, cards in sorted(grouped.items())
    ]
    return Board(settings, tuple(result), chosen, tuple(known), notice, names)
