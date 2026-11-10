"""Negative-fixture harness for spec validation rules (tasks T004).

A fixture folder ``tests/fixtures/specs/<name>/`` holds:

- ``patch.yaml``: a list of operations applied to a copy of ``_valid``::

      - {file: terminals/T0.yaml, op: set, path: /terminal/metadata/version, value: "0.9.0"}
      - {file: terminals/T0.yaml, op: delete, path: /terminal/timeline/clarification_sla}
      - {file: terminals/T0.yaml, op: append, path: /terminal/trigger/on, value: X.y}
      - {file: shared/bad.yaml, op: write_text, value: "a: [\\n"}

- ``expected.yaml``: findings that must appear::

      - {rule_id: S-01, file: terminals/T0.yaml, path_contains: /terminal/timeline}

Paths are JSON pointers (``/a/b/0``). ``set`` creates missing mapping keys.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "specs"
VALID = FIXTURES / "_valid"


@dataclass(frozen=True)
class Expected:
    rule_id: str
    file: str | None
    path_contains: str | None
    severity: str | None


def _yaml() -> YAML:
    yaml = YAML()  # round-trip, keeps comments and order
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def _tokens(pointer: str) -> list[str]:
    if pointer in ("", "/"):
        return []
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer.lstrip("/").split("/")]


def _step(node: Any, token: str) -> Any:
    if isinstance(node, list):
        return node[int(token)]
    return node[token]


def _apply(data: Any, op: str, pointer: str, value: Any) -> None:
    tokens = _tokens(pointer)
    parent = data
    for token in tokens[:-1]:
        if isinstance(parent, dict) and token not in parent and op == "set":
            parent[token] = {}
        parent = _step(parent, token)
    last = tokens[-1] if tokens else None
    if op == "set":
        assert last is not None
        if isinstance(parent, list):
            parent[int(last)] = value
        else:
            parent[last] = value
    elif op == "delete":
        assert last is not None
        if isinstance(parent, list):
            del parent[int(last)]
        else:
            del parent[last]
    elif op == "append":
        target = _step(parent, last) if last is not None else parent
        target.append(value)
    else:
        raise ValueError(f"unknown op {op}")


def build_bundle(tmp_path: Path, fixture: str | None = None) -> Path:
    """Copy ``_valid`` to ``tmp_path/adlc-specs`` and apply the fixture's patch."""
    root = tmp_path / "adlc-specs"
    shutil.copytree(VALID, root)
    if fixture is None:
        return root
    yaml = _yaml()
    patch_file = FIXTURES / fixture / "patch.yaml"
    operations = yaml.load(patch_file.read_text()) or []
    for operation in operations:
        target = root / str(operation["file"])
        if operation["op"] == "write_text":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(operation["value"]))
            continue
        if operation["op"] == "remove_file":
            target.unlink()
            continue
        data = yaml.load(target.read_text())
        _apply(data, str(operation["op"]), str(operation.get("path", "")), operation.get("value"))
        with target.open("w") as handle:
            yaml.dump(data, handle)
    return root


def expected_findings(fixture: str) -> list[Expected]:
    data = _yaml().load((FIXTURES / fixture / "expected.yaml").read_text()) or []
    return [
        Expected(
            rule_id=str(item["rule_id"]),
            file=item.get("file"),
            path_contains=item.get("path_contains"),
            severity=item.get("severity"),
        )
        for item in data
    ]


def fixture_names() -> list[str]:
    return sorted(p.name for p in FIXTURES.iterdir() if p.is_dir() and not p.name.startswith("_"))
