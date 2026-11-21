"""Seed file validation and loading (contracts/cli-settings-seed.md, research R-10).

The seed describes the organisation, project, area tree, process (types, states, fields) and
identities. It never holds tokens: any key named like a secret is refused (FR-017).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ado_sim.db import Database
from ado_sim.process import (
    FIELD_TYPES,
    STATE_CATEGORIES,
    SYSTEM_FIELD_NAMES,
    SYSTEM_FIELDS,
    BoardSettings,
)

_NAMESPACE = uuid.UUID("6f1c5c0e-5a43-4c55-9d0e-0a6f0d1d2b15")
_REFERENCE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
_SECRET_KEY = re.compile(r"token|secret|password|passwd|credential|\bpat\b", re.IGNORECASE)
_TOP_KEYS = {"organization", "project", "areas", "process", "identities", "board"}
_REFRESH = re.compile(r"^(\d+)s$")
REFRESH_RANGE = (2, 60)
_PROCESS_KEYS = {"agile_states", "types", "custom_fields"}
_TYPE_KEYS = {"reference_name", "description", "color", "states", "fields"}


class SeedError(ValueError):
    """The seed file is invalid or cannot be loaded."""


class SeedRefusedError(SeedError):
    """The database already holds a board; seeding would mix two."""


@dataclass(frozen=True)
class SeedState:
    name: str
    category: str
    color: str


@dataclass(frozen=True)
class SeedType:
    name: str
    reference_name: str
    description: str
    color: str
    states: tuple[SeedState, ...]
    fields: tuple[tuple[str, tuple[Any, ...] | None], ...]


@dataclass(frozen=True)
class SeedField:
    reference_name: str
    name: str
    type: str


@dataclass(frozen=True)
class SeedIdentity:
    id: str
    unique_name: str
    display_name: str
    service: bool = False  # 017: the platform's service account never signs in to pages


@dataclass(frozen=True)
class Seed:
    organization_id: str
    organization: str
    project_id: str
    project: str
    areas: tuple[str, ...]
    types: tuple[SeedType, ...]
    fields: tuple[SeedField, ...]
    identities: tuple[SeedIdentity, ...]
    board: BoardSettings | None = None


def _stable_id(kind: str, name: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{kind}:{name.lower()}"))


def _check_keys(node: Any, where: str = "seed") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and _SECRET_KEY.search(key):
                raise SeedError(f"{where}: key '{key}' looks like a secret; seeds hold no tokens")
            _check_keys(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _check_keys(value, f"{where}[{index}]")


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SeedError(f"{where} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, where: str, allowed: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SeedError(f"{where} must be a mapping")
    if allowed is not None:
        unknown = sorted(str(k) for k in value if k not in allowed)
        if unknown:
            raise SeedError(f"{where}: unknown key(s) {', '.join(unknown)}")
    return dict(value)


def _states(value: Any, where: str) -> tuple[SeedState, ...]:
    if not isinstance(value, list) or not value:
        raise SeedError(f"{where}: states must be a non-empty list")
    states: list[SeedState] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        entry = _mapping(item, f"{where}[{index}]", {"name", "category", "color"})
        name = _text(entry.get("name"), f"{where}[{index}].name")
        category = entry.get("category")
        if category not in STATE_CATEGORIES:
            raise SeedError(
                f"{where}[{index}]: category must be one of {', '.join(STATE_CATEGORIES)}"
            )
        if name.lower() in seen:
            raise SeedError(f"{where}: duplicate state '{name}'")
        seen.add(name.lower())
        states.append(SeedState(name, str(category), str(entry.get("color") or "b2b2b2")))
    return tuple(states)


def _areas(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SeedError("areas must be a list of paths under the project")
    paths: list[str] = []
    for index, item in enumerate(value):
        path = _text(item, f"areas[{index}]")
        segments = path.split("\\")
        if path.startswith("\\") or any(not s.strip() or s.strip() == ".." for s in segments):
            raise SeedError(
                f"areas[{index}]: area path '{path}' must be relative to the project root"
            )
        normalised = "\\".join(s.strip() for s in segments)
        if normalised.lower() in (p.lower() for p in paths):
            raise SeedError(f"areas[{index}]: duplicate area path '{path}'")
        paths.append(normalised)
    return tuple(paths)


def parse_seed(data: Any) -> Seed:
    _check_keys(data)
    top = _mapping(data, "seed", _TOP_KEYS)
    organization = _text(top.get("organization"), "organization")
    project = _text(top.get("project"), "project")
    areas = _areas(top.get("areas"))
    process = _mapping(top.get("process"), "process", _PROCESS_KEYS)

    fields: list[SeedField] = []
    for ref, spec in _mapping(process.get("custom_fields") or {}, "process.custom_fields").items():
        ref = str(ref)
        where = f"process.custom_fields.{ref}"
        if not _REFERENCE_NAME.match(ref):
            raise SeedError(f"{where}: invalid reference name")
        if ref.lower() in SYSTEM_FIELD_NAMES:
            raise SeedError(f"{where}: {ref} is a system field and cannot be redefined")
        entry = _mapping(spec, where, {"type", "name"})
        kind = entry.get("type")
        if kind not in FIELD_TYPES:
            raise SeedError(f"{where}: field type must be one of {', '.join(FIELD_TYPES)}")
        name = str(entry.get("name") or ref.rsplit(".", 1)[-1])
        fields.append(SeedField(ref, name, str(kind)))
    known = {f.reference_name.lower() for f in fields} | SYSTEM_FIELD_NAMES

    agile = process.get("agile_states")
    agile_states = _states(agile, "process.agile_states") if agile is not None else None

    types: list[SeedType] = []
    raw_types = _mapping(process.get("types"), "process.types")
    if not raw_types:
        raise SeedError("process.types must define at least one work item type")
    for type_name, spec in raw_types.items():
        name = _text(type_name, "process.types key")
        where = f"process.types.{name}"
        entry = _mapping(spec, where, _TYPE_KEYS)
        raw_states = entry.get("states")
        if raw_states == "agile":
            if agile_states is None:
                raise SeedError(f"{where}: states 'agile' needs process.agile_states")
            states = agile_states
        else:
            states = _states(raw_states, f"{where}.states")
        type_fields: list[tuple[str, tuple[Any, ...] | None]] = []
        for index, item in enumerate(entry.get("fields") or []):
            if isinstance(item, dict):
                field_entry = _mapping(item, f"{where}.fields[{index}]", {"ref", "allowed_values"})
                ref = _text(field_entry.get("ref"), f"{where}.fields[{index}].ref")
                allowed = field_entry.get("allowed_values")
                if allowed is not None and (not isinstance(allowed, list) or not allowed):
                    raise SeedError(f"{where}.fields[{index}]: allowed_values must be a list")
                values = tuple(allowed) if allowed is not None else None
            else:
                ref = _text(item, f"{where}.fields[{index}]")
                values = None
            if ref.lower() not in known:
                raise SeedError(f"{where}: field {ref} is not defined in process.custom_fields")
            type_fields.append((ref, values))
        types.append(
            SeedType(
                name=name,
                reference_name=str(
                    entry.get("reference_name")
                    or "Microsoft.VSTS.WorkItemTypes." + name.replace(" ", "")
                ),
                description=str(entry.get("description") or ""),
                color=str(entry.get("color") or "009CCC"),
                states=states,
                fields=tuple(type_fields),
            )
        )

    identities: list[SeedIdentity] = []
    raw_identities = top.get("identities")
    if not isinstance(raw_identities, list) or not raw_identities:
        raise SeedError("identities must be a non-empty list")
    for index, item in enumerate(raw_identities):
        entry = _mapping(item, f"identities[{index}]", {"unique_name", "display_name", "service"})
        unique = _text(entry.get("unique_name"), f"identities[{index}].unique_name")
        display = _text(entry.get("display_name"), f"identities[{index}].display_name")
        if unique.lower() in (i.unique_name.lower() for i in identities):
            raise SeedError(f"identities[{index}]: duplicate unique name '{unique}'")
        service = entry.get("service", False)
        if not isinstance(service, bool):
            raise SeedError(f"identities[{index}].service must be true or false")
        identities.append(SeedIdentity(_stable_id("identity", unique), unique, display, service))
    if sum(1 for i in identities if i.service) > 1:
        raise SeedError("identities: at most one identity is the service account (service: true)")

    return Seed(
        organization_id=_stable_id("organization", organization),
        organization=organization,
        project_id=_stable_id("project", f"{organization}/{project}"),
        project=project,
        areas=areas,
        types=tuple(types),
        fields=tuple(fields),
        identities=tuple(identities),
        board=_board(top.get("board"), types),
    )


def _board(value: Any, types: list[SeedType]) -> BoardSettings | None:
    if value is None:
        return None
    entry = _mapping(value, "board", {"type", "card_fields", "collapsed_states", "refresh"})
    type_name = _text(entry.get("type"), "board.type")
    kind = next((t for t in types if t.name.lower() == type_name.lower()), None)
    if kind is None:
        raise SeedError(f"board.type: '{type_name}' is not a work item type of the process")
    own = {ref.lower() for ref, _ in kind.fields} | SYSTEM_FIELD_NAMES
    card_fields = []
    for index, ref in enumerate(entry.get("card_fields") or []):
        name = _text(ref, f"board.card_fields[{index}]")
        if name.lower() not in own:
            raise SeedError(f"board.card_fields[{index}]: '{name}' is not a field of {kind.name}")
        card_fields.append(name)
    states = {state.name.lower(): state.name for state in kind.states}
    collapsed = []
    for index, state in enumerate(entry.get("collapsed_states") or []):
        name = _text(state, f"board.collapsed_states[{index}]")
        if name.lower() not in states:
            raise SeedError(
                f"board.collapsed_states[{index}]: '{name}' is not a state of {kind.name}"
            )
        collapsed.append(states[name.lower()])
    match = _REFRESH.match(str(entry.get("refresh", "5s")).strip())
    seconds = int(match.group(1)) if match else 0
    if not REFRESH_RANGE[0] <= seconds <= REFRESH_RANGE[1]:
        raise SeedError(
            f"board.refresh must be <seconds>s between {REFRESH_RANGE[0]}s and {REFRESH_RANGE[1]}s"
        )
    return BoardSettings(kind.name, tuple(card_fields), tuple(collapsed), seconds)


def read_seed(path: Path) -> Seed:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SeedError(f"cannot read seed file {path}: {error.strerror}") from error
    try:
        data = YAML(typ="safe").load(text)
    except YAMLError as error:
        raise SeedError(f"seed file {path} is not valid YAML (duplicate key or syntax)") from error
    return parse_seed(data)


def is_seeded(db: Database) -> bool:
    with db.read() as conn:
        return conn.execute("SELECT 1 FROM organization").fetchone() is not None


def load_seed(db: Database, path: Path) -> Seed:
    """Validate the file and load it into an empty database in one transaction."""
    seed = read_seed(path)
    with db.write() as conn:
        if conn.execute("SELECT 1 FROM organization").fetchone():
            raise SeedRefusedError("the simulator is already seeded; use `ado-sim reset --yes`")
        if conn.execute("SELECT 1 FROM work_item").fetchone():
            raise SeedRefusedError("work items exist; use `ado-sim reset --yes`")
        conn.execute(
            "INSERT INTO organization (id, name) VALUES (?, ?)",
            (seed.organization_id, seed.organization),
        )
        conn.execute(
            "INSERT INTO project (id, organization_id, name) VALUES (?, ?, ?)",
            (seed.project_id, seed.organization_id, seed.project),
        )
        node_ids: dict[str, int] = {}

        def add_node(path_text: str, name: str, parent: int | None) -> int:
            cursor = conn.execute(
                "INSERT INTO area_node (identifier, project_id, name, path, parent_id)"
                " VALUES (?, ?, ?, ?, ?)",
                (_stable_id("area", path_text), seed.project_id, name, path_text, parent),
            )
            node_ids[path_text.lower()] = int(cursor.lastrowid or 0)
            return node_ids[path_text.lower()]

        root = add_node(seed.project, seed.project, None)
        for relative in seed.areas:
            parent, full = root, seed.project
            for segment in relative.split("\\"):
                full = f"{full}\\{segment}"
                if full.lower() not in node_ids:
                    add_node(full, segment, parent)
                parent = node_ids[full.lower()]

        for field in SYSTEM_FIELDS:
            conn.execute(
                "INSERT INTO field (reference_name, name, type, read_only) VALUES (?, ?, ?, ?)",
                (field.reference_name, field.name, field.type, int(field.read_only)),
            )
        for custom in seed.fields:
            conn.execute(
                "INSERT INTO field (reference_name, name, type, read_only) VALUES (?, ?, ?, 0)",
                (custom.reference_name, custom.name, custom.type),
            )
        canonical = {f.reference_name.lower(): f.reference_name for f in SYSTEM_FIELDS}
        canonical.update({f.reference_name.lower(): f.reference_name for f in seed.fields})
        for ordinal, kind in enumerate(seed.types):
            conn.execute(
                "INSERT INTO work_item_type (name, reference_name, description, color, ordinal)"
                " VALUES (?, ?, ?, ?, ?)",
                (kind.name, kind.reference_name, kind.description, kind.color, ordinal),
            )
            for index, state in enumerate(kind.states):
                conn.execute(
                    "INSERT INTO work_item_type_state (type_name, name, category, color, ordinal)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (kind.name, state.name, state.category, state.color, index),
                )
            assigned: dict[str, tuple[Any, ...] | None] = {
                f.reference_name: None for f in SYSTEM_FIELDS
            }
            for ref, allowed in kind.fields:
                assigned[canonical[ref.lower()]] = allowed
            for ref, allowed in assigned.items():
                conn.execute(
                    "INSERT INTO work_item_type_field (type_name, reference_name, allowed_values)"
                    " VALUES (?, ?, ?)",
                    (kind.name, ref, json.dumps(list(allowed)) if allowed is not None else None),
                )
        for identity in seed.identities:
            conn.execute(
                "INSERT INTO identity (id, display_name, unique_name, is_service)"
                " VALUES (?, ?, ?, ?)",
                (identity.id, identity.display_name, identity.unique_name, int(identity.service)),
            )
        if seed.board is not None:
            for key, value in (
                ("type", seed.board.type),
                ("card_fields", list(seed.board.card_fields)),
                ("collapsed_states", list(seed.board.collapsed_states)),
                ("refresh_seconds", seed.board.refresh_seconds),
            ):
                conn.execute(
                    "INSERT INTO board_setting (key, value) VALUES (?, ?)", (key, json.dumps(value))
                )
    return seed
