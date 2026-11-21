"""Board-neutral types (data-model.md "Board-neutral types").

Field references (the keys of ``fields``) and item types are opaque strings to everything outside
an adapter: they come from the tracker mapping, never from code (FR-003).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BoardItem:
    """A work item as the board holds it at one revision."""

    id: int
    rev: int
    type: str
    fields: Mapping[str, Any]
    parent_id: int | None = None
    changed_by: str | None = None  # the board unique name of the identity that made ``rev``


@dataclass(frozen=True)
class FieldChange:
    old: Any
    new: Any


@dataclass(frozen=True)
class BoardUpdate:
    """One change to one item, as inbound sync reads it (one ADO "update")."""

    item_id: int
    update_id: int  # unique per item, increasing; the idempotency key with item_id (FR-012)
    rev: int  # the item's revision after the update; unchanged by a link's other side
    changed_by: str  # board unique name, lower case
    fields: Mapping[str, FieldChange] = field(default_factory=dict)
    parent_added: int | None = None
    parent_removed: int | None = None

    @property
    def is_revision(self) -> bool:
        """False for an update that records only the other side of a link (015 T001)."""
        return bool(self.fields)


@dataclass(frozen=True)
class ChangePage:
    """Items changed at or after a watermark, and the board's ``as_of`` for the next poll."""

    item_ids: tuple[int, ...]
    as_of: str


@dataclass(frozen=True)
class Identity:
    unique_name: str
    display_name: str
    id: str


@dataclass(frozen=True)
class ItemWrite:
    """Fields to set and to clear, all or nothing, only if the item is still at ``expected_rev``."""

    set: Mapping[str, Any] = field(default_factory=dict)
    clear: tuple[str, ...] = ()
    expected_rev: int | None = None


@dataclass(frozen=True)
class BoardType:
    name: str
    states: tuple[str, ...]
    fields: frozenset[str]


@dataclass(frozen=True)
class BoardInfo:
    """What the board offers: its process (types, states, fields) and its area paths."""

    types: Mapping[str, BoardType]
    areas: frozenset[str]
