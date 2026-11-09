"""Role catalogue loader (TDS §3, FR-019). Role ids are data, never code constants."""

import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

ROLE_ID = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


class CatalogueError(ValueError):
    """The role catalogue file is missing, malformed or inconsistent."""


def _load_yaml(path: Path) -> Any:
    try:
        return YAML(typ="safe").load(path.read_text())
    except (OSError, YAMLError) as exc:
        raise CatalogueError(f"{path}: cannot read role catalogue ({type(exc).__name__})") from None


def load_role_ids(path: Path) -> frozenset[str]:
    data = _load_yaml(path)
    roles = data.get("roles") if isinstance(data, dict) else None
    if not isinstance(roles, list):
        raise CatalogueError(f"{path}: expected a 'roles' list")
    if not roles:
        raise CatalogueError(f"{path}: no roles defined")
    ids: set[str] = set()
    for index, entry in enumerate(roles):
        if not isinstance(entry, dict):
            raise CatalogueError(f"{path}: roles[{index}] is not a mapping")
        role_id = entry.get("id")
        description = entry.get("description")
        if not isinstance(role_id, str) or not ROLE_ID.match(role_id):
            raise CatalogueError(f"{path}: roles[{index}] id {role_id!r} is not snake_case")
        if not isinstance(description, str) or not description.strip():
            raise CatalogueError(f"{path}: role {role_id} has no description")
        if role_id in ids:
            raise CatalogueError(f"{path}: duplicate role id {role_id}")
        ids.add(role_id)
    return frozenset(ids)
