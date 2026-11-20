"""The process (types, states, fields), the area tree and identities: definitions and reads.

The system fields below are part of the ADO contract (their reference names and semantics are
ADO's), so they live in code; everything specific to a board (types, states, custom fields,
areas, identities) comes from the seed file.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

STATE_CATEGORIES = ("Proposed", "InProgress", "Resolved", "Completed", "Removed")
FIELD_TYPES = (
    "string",
    "plainText",
    "html",
    "integer",
    "double",
    "dateTime",
    "boolean",
    "identity",
    "treePath",
    "history",
)


@dataclass(frozen=True)
class FieldDef:
    reference_name: str
    name: str
    type: str
    read_only: bool
    allowed_values: tuple[Any, ...] | None = None


# (reference name, friendly name, type, read only): set by the simulator when read only.
SYSTEM_FIELDS: tuple[FieldDef, ...] = tuple(
    FieldDef(ref, name, kind, read_only)
    for ref, name, kind, read_only in (
        ("System.Id", "ID", "integer", True),
        ("System.Rev", "Rev", "integer", True),
        ("System.WorkItemType", "Work Item Type", "string", True),
        ("System.TeamProject", "Team Project", "string", True),
        ("System.Title", "Title", "string", False),
        ("System.Description", "Description", "html", False),
        ("System.State", "State", "string", False),
        ("System.Reason", "Reason", "string", False),
        ("System.AreaPath", "Area Path", "treePath", False),
        ("System.AssignedTo", "Assigned To", "identity", False),
        ("System.Tags", "Tags", "plainText", False),
        ("System.CreatedBy", "Created By", "identity", True),
        ("System.CreatedDate", "Created Date", "dateTime", True),
        ("System.ChangedBy", "Changed By", "identity", True),
        ("System.ChangedDate", "Changed Date", "dateTime", True),
        ("System.CommentCount", "Comment Count", "integer", True),
        ("System.History", "History", "history", True),
    )
)
SYSTEM_FIELD_NAMES = frozenset(f.reference_name.lower() for f in SYSTEM_FIELDS)


@dataclass(frozen=True)
class Identity:
    id: str
    display_name: str
    unique_name: str
    active: bool = True

    def reference(self) -> dict[str, str]:
        """The stored form of an identity field value (rendered with URLs on read)."""
        return {"displayName": self.display_name, "id": self.id, "uniqueName": self.unique_name}


@dataclass(frozen=True)
class ProjectInfo:
    organization_id: str
    organization: str
    project_id: str
    project: str


@dataclass(frozen=True)
class TypeInfo:
    name: str
    reference_name: str
    description: str
    color: str
    states: tuple[tuple[str, str, str], ...]  # (name, category, color)
    fields: dict[str, FieldDef]  # keyed by lower-case reference name

    @property
    def state_names(self) -> list[str]:
        return [state[0] for state in self.states]

    def field(self, reference_name: str) -> FieldDef | None:
        return self.fields.get(reference_name.lower())


def project_info(conn: sqlite3.Connection) -> ProjectInfo | None:
    row = conn.execute(
        "SELECT o.id AS oid, o.name AS oname, p.id AS pid, p.name AS pname"
        " FROM project p JOIN organization o ON o.id = p.organization_id"
    ).fetchone()
    if row is None:
        return None
    return ProjectInfo(row["oid"], row["oname"], row["pid"], row["pname"])


def all_fields(conn: sqlite3.Connection) -> dict[str, FieldDef]:
    return {
        row["reference_name"].lower(): FieldDef(
            row["reference_name"], row["name"], row["type"], bool(row["read_only"])
        )
        for row in conn.execute("SELECT * FROM field ORDER BY reference_name")
    }


def type_names(conn: sqlite3.Connection) -> list[str]:
    return [row["name"] for row in conn.execute("SELECT name FROM work_item_type ORDER BY ordinal")]


def type_info(conn: sqlite3.Connection, name: str) -> TypeInfo | None:
    row = conn.execute("SELECT * FROM work_item_type WHERE name = ?", (name,)).fetchone()
    if row is None:
        return None
    states = tuple(
        (s["name"], s["category"], s["color"])
        for s in conn.execute(
            "SELECT * FROM work_item_type_state WHERE type_name = ? ORDER BY ordinal",
            (row["name"],),
        )
    )
    fields = {
        f["reference_name"].lower(): FieldDef(
            f["reference_name"],
            f["name"],
            f["type"],
            bool(f["read_only"]),
            tuple(json.loads(f["allowed_values"])) if f["allowed_values"] else None,
        )
        for f in conn.execute(
            "SELECT f.reference_name, f.name, f.type, f.read_only, t.allowed_values"
            " FROM work_item_type_field t JOIN field f ON f.reference_name = t.reference_name"
            " WHERE t.type_name = ? ORDER BY f.reference_name",
            (row["name"],),
        )
    }
    return TypeInfo(
        row["name"], row["reference_name"], row["description"], row["color"], states, fields
    )


def area_paths(conn: sqlite3.Connection) -> dict[str, str]:
    """Lower-case path to stored path."""
    return {row["path"].lower(): row["path"] for row in conn.execute("SELECT path FROM area_node")}


def identity_by_id(conn: sqlite3.Connection, identity_id: str) -> Identity | None:
    row = conn.execute("SELECT * FROM identity WHERE id = ?", (identity_id,)).fetchone()
    return _identity(row) if row else None


def identity_by_name(conn: sqlite3.Connection, name: str) -> Identity | None:
    """Resolve a unique name, a display name or ``Display Name <unique name>``."""
    text = name.strip()
    if text.endswith(">") and "<" in text:
        text = text[text.rindex("<") + 1 : -1].strip()
    row = conn.execute(
        "SELECT * FROM identity WHERE unique_name = ? COLLATE NOCASE", (text,)
    ).fetchone()
    if row is None:
        rows = conn.execute(
            "SELECT * FROM identity WHERE display_name = ? COLLATE NOCASE", (text,)
        ).fetchall()
        row = rows[0] if len(rows) == 1 else None
    return _identity(row) if row else None


def _identity(row: sqlite3.Row) -> Identity:
    return Identity(row["id"], row["display_name"], row["unique_name"], bool(row["active"]))
