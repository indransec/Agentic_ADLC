"""ADO's JSON Patch dialect for work items (research R-07).

``apply_patch`` validates a whole patch against the item's type and current values and returns
the new values without touching the database; any invalid operation refuses the whole patch.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ado_sim.db import format_time
from ado_sim.errors import AdoError, conflict, invalid
from ado_sim.process import FieldDef, Identity, TypeInfo

MAX_OPERATIONS = 500
MAX_VALUE_BYTES = 1024 * 1024
MAX_STRING_CHARS = 255
REQUIRED_FIELDS = ("System.Title", "System.State", "System.AreaPath")

RELATION_TYPES = {
    "System.LinkTypes.Hierarchy-Forward": ("System.LinkTypes.Hierarchy-Reverse", "Child"),
    "System.LinkTypes.Hierarchy-Reverse": ("System.LinkTypes.Hierarchy-Forward", "Parent"),
    "System.LinkTypes.Dependency-Forward": ("System.LinkTypes.Dependency-Reverse", "Successor"),
    "System.LinkTypes.Dependency-Reverse": ("System.LinkTypes.Dependency-Forward", "Predecessor"),
}
_CANONICAL_RELATION = {name.lower(): name for name in RELATION_TYPES}
_TARGET = re.compile(r"/_apis/wit/workitems/(\d+)/?$", re.IGNORECASE)
_RELATION_INDEX = re.compile(r"^/relations/(\d+)$")


@dataclass(frozen=True)
class Relation:
    rel: str
    target_id: int
    attributes: dict[str, Any] = field(default_factory=lambda: {"isLocked": False}, hash=False)

    def same_link(self, other: Relation) -> bool:
        return self.rel == other.rel and self.target_id == other.target_id

    def stored(self) -> dict[str, Any]:
        return {"rel": self.rel, "targetId": self.target_id, "attributes": self.attributes}

    @staticmethod
    def from_stored(data: dict[str, Any]) -> Relation:
        return Relation(data["rel"], int(data["targetId"]), dict(data["attributes"]))


@dataclass
class PatchResult:
    fields: dict[str, Any]
    relations: list[Relation]
    added: list[Relation]
    removed: list[Relation]
    original_fields: dict[str, Any]
    original_relations: list[Relation]

    @property
    def changed(self) -> bool:
        return self.fields != self.original_fields or self.relations != self.original_relations


def relation_target(url: Any) -> int | None:
    if not isinstance(url, str):
        return None
    match = _TARGET.search(url)
    return int(match.group(1)) if match else None


def apply_patch(
    operations: Any,
    *,
    kind: TypeInfo,
    fields: dict[str, Any],
    relations: list[Relation],
    rev: int | None,
    area_paths: dict[str, str],
    resolve_identity: Callable[[str], Identity | None],
) -> PatchResult:
    if not isinstance(operations, list):
        raise invalid("The request body must be a JSON Patch document: a JSON array of operations.")
    if not operations:
        raise invalid("The JSON Patch document holds no operations.")
    if len(operations) > MAX_OPERATIONS:
        raise invalid(f"A patch may hold at most {MAX_OPERATIONS} operations.")
    new_fields = dict(fields)
    new_relations = list(relations)
    added: list[Relation] = []
    removed: list[Relation] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise invalid(f"Operation {index} is not a JSON object.")
        kind_of = operation.get("op")
        path = operation.get("path")
        if kind_of not in ("add", "replace", "remove", "test") or not isinstance(path, str):
            raise invalid(
                f"Operation {index}: op must be add, replace, remove or test, with a path."
            )
        value = operation.get("value")
        if path == "/rev":
            if kind_of != "test":
                raise invalid("The revision can only be tested (op 'test', path '/rev').")
            if rev is None:
                raise invalid("A new work item has no revision to test.")
            if value != rev:
                raise conflict(
                    f"The work item is at revision {rev}; the patch tested revision {value}. "
                    "Read the work item again and reapply the change."
                )
        elif path.startswith("/fields/"):
            _field_operation(
                kind_of,
                path[len("/fields/") :],
                value,
                kind,
                new_fields,
                area_paths,
                resolve_identity,
            )
        elif path == "/relations/-":
            if kind_of != "add":
                raise invalid("Relations are added with op 'add' on '/relations/-'.")
            relation = _relation(value, index)
            if any(existing.same_link(relation) for existing in new_relations):
                raise invalid(
                    f"The relation {relation.rel} to {relation.target_id} already exists."
                )
            new_relations.append(relation)
            added.append(relation)
        elif match := _RELATION_INDEX.match(path):
            if kind_of != "remove":
                raise invalid("Only 'remove' is supported on '/relations/<index>'.")
            position = int(match.group(1))
            if position >= len(new_relations):
                raise invalid(f"There is no relation at index {position}.")
            gone = new_relations.pop(position)
            if gone in added:
                added.remove(gone)
            else:
                removed.append(gone)
        else:
            raise invalid(f"Operation {index}: the path '{path}' is not supported.")
    return PatchResult(new_fields, new_relations, added, removed, dict(fields), list(relations))


def _field_operation(
    kind_of: str,
    reference: str,
    value: Any,
    kind: TypeInfo,
    fields: dict[str, Any],
    area_paths: dict[str, str],
    resolve_identity: Callable[[str], Identity | None],
) -> None:
    definition = kind.field(reference)
    if definition is None:
        raise invalid(
            f"TF51535: Cannot find field {reference} on work item type {kind.name}.",
            "FieldNotFoundException",
        )
    ref = definition.reference_name
    if kind_of == "test":
        if fields.get(ref) != _convert(definition, value, kind, area_paths, resolve_identity):
            raise conflict(f"The test of field {ref} failed: its current value differs.")
        return
    if definition.read_only:
        raise invalid(
            f"The field {ref} is read-only and set by the simulator.", "ReadOnlyFieldException"
        )
    if kind_of == "remove" or value is None or value == "":
        if ref in REQUIRED_FIELDS:
            raise invalid(
                f"The field {ref} is required and cannot be removed.", "RuleValidationException"
            )
        fields.pop(ref, None)
        return
    fields[ref] = _convert(definition, value, kind, area_paths, resolve_identity)


def _convert(
    definition: FieldDef,
    value: Any,
    kind: TypeInfo,
    area_paths: dict[str, str],
    resolve_identity: Callable[[str], Identity | None],
) -> Any:
    ref = definition.reference_name

    def refuse(reason: str) -> AdoError:
        return invalid(f"The value for {ref} is invalid: {reason}.", "RuleValidationException")

    kind_name = definition.type
    if kind_name in ("string", "plainText", "html"):
        if not isinstance(value, str):
            raise refuse("expected text")
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
            raise refuse("larger than 1 MB")
        if kind_name == "string" and len(value) > MAX_STRING_CHARS:
            raise refuse(f"string fields hold at most {MAX_STRING_CHARS} characters")
        converted: Any = value
        if ref == "System.State":
            converted = _one_of(value, kind.state_names, refuse)
    elif kind_name == "integer":
        if isinstance(value, bool) or not isinstance(value, int | str):
            raise refuse("expected an integer")
        try:
            converted = int(value)
        except ValueError as error:
            raise refuse("expected an integer") from error
    elif kind_name == "double":
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise refuse("expected a number")
        try:
            converted = float(value)
        except ValueError as error:
            raise refuse("expected a number") from error
    elif kind_name == "boolean":
        if isinstance(value, bool):
            converted = value
        elif isinstance(value, str) and value.lower() in ("true", "false"):
            converted = value.lower() == "true"
        else:
            raise refuse("expected true or false")
    elif kind_name == "dateTime":
        converted = format_time(_parse_datetime(value, refuse))
    elif kind_name == "identity":
        name = value.get("uniqueName") if isinstance(value, dict) else value
        identity = resolve_identity(name) if isinstance(name, str) else None
        if identity is None:
            raise refuse("unknown identity")
        converted = identity.reference()
    else:  # treePath
        if not isinstance(value, str) or value.lower() not in area_paths:
            raise invalid(
                f"TF401347: Invalid tree name given for work item, field '{ref}'.",
                "RuleValidationException",
            )
        converted = area_paths[value.lower()]
    if definition.allowed_values is not None:
        converted = _one_of(converted, list(definition.allowed_values), refuse)
    if len(json.dumps(converted).encode("utf-8")) > MAX_VALUE_BYTES + 2:
        raise refuse("larger than 1 MB")
    return converted


def _one_of(value: Any, allowed: list[Any], refuse: Callable[[str], AdoError]) -> Any:
    for candidate in allowed:
        if candidate == value or (
            isinstance(candidate, str)
            and isinstance(value, str)
            and candidate.lower() == value.lower()
        ):
            return candidate
    raise refuse("allowed values are " + ", ".join(str(a) for a in allowed))


def _parse_datetime(value: Any, refuse: Callable[[str], AdoError]) -> datetime:
    if not isinstance(value, str):
        raise refuse("expected an ISO 8601 date and time")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise refuse("expected an ISO 8601 date and time") from error
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _relation(value: Any, index: int) -> Relation:
    if not isinstance(value, dict):
        raise invalid(f"Operation {index}: a relation is an object with rel and url.")
    rel = _CANONICAL_RELATION.get(str(value.get("rel", "")).lower())
    if rel is None:
        raise invalid(
            f"Operation {index}: the link type {value.get('rel')!r} is not supported; supported: "
            + ", ".join(RELATION_TYPES),
        )
    target = relation_target(value.get("url"))
    if target is None:
        raise invalid(f"Operation {index}: the relation url must name a work item.")
    attributes: dict[str, Any] = {"isLocked": False}
    raw = value.get("attributes") or {}
    if not isinstance(raw, dict):
        raise invalid(f"Operation {index}: relation attributes must be an object.")
    comment = raw.get("comment")
    if comment is not None:
        if not isinstance(comment, str) or len(comment.encode("utf-8")) > MAX_VALUE_BYTES:
            raise invalid(f"Operation {index}: the relation comment must be text under 1 MB.")
        attributes["comment"] = comment
    return Relation(rel, target, attributes)
