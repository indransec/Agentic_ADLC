"""Tables imported from a recorded tool result (feature 011, research R-08,
contracts/artifact-import.md).

For a per-case table (hundreds of rows a model cannot copy reliably) the agent names a result it
received in this run and how cases trace to requirements; the platform expands the rows from the
recorded result. The agent decides (which result, which mapping); the values are the measured ones.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

CASE_COLUMNS = ("case_id", "req_id", "expected", "actual", "score", "result")


@dataclass(frozen=True)
class ImportSource:
    """A recorded result of this run that offers case rows."""

    result_id: str
    kind: str
    sha256: str
    cases: list[Mapping[str, Any]]


@dataclass(frozen=True)
class ArtifactImport:
    artifact: str
    result_id: str
    kind: str
    sha256: str
    req_id_by: Mapping[str, Any]
    rows: int


Resolver = Callable[[str], ImportSource | None]


def is_import(value: Any) -> bool:
    return isinstance(value, Mapping) and set(value) == {"import"}


def _joined(value: Any) -> str:
    if isinstance(value, Mapping):
        return "; ".join(f"{k}={v}" for k, v in value.items())
    return "" if value is None else str(value)


def expand(
    artifact: str, columns: tuple[str, ...], value: Mapping[str, Any], resolve: Resolver | None
) -> tuple[list[dict[str, Any]], ArtifactImport | None, list[str]]:
    """The rows, the provenance and any problems (problems are returned to the agent)."""
    spec = value.get("import")
    if not isinstance(spec, Mapping):
        return [], None, [f"{artifact}: import must be an object with result and req_id_by"]
    if tuple(columns) != CASE_COLUMNS:
        return (
            [],
            None,
            [f"{artifact}: only a table with columns {list(CASE_COLUMNS)} can be imported"],
        )
    result_id, mapping = str(spec.get("result") or ""), spec.get("req_id_by")
    if not isinstance(mapping, Mapping) or not mapping.get("field"):
        return [], None, [f"{artifact}: req_id_by needs a field, a map and a default"]
    source = resolve(result_id) if resolve is not None and result_id else None
    if source is None:
        return (
            [],
            None,
            [f"{artifact}: {result_id or 'the result'} is not a case result of this run"],
        )
    field, table = str(mapping["field"]), dict(mapping.get("map") or {})
    default = mapping.get("default")
    rows: list[dict[str, Any]] = []
    for case in source.cases:
        expected = case.get("expected") or {}
        key = str(expected.get(field)) if isinstance(expected, Mapping) else ""
        req = table.get(key, default)
        if not req:
            return [], None, [f"{artifact}: no requirement for {field}={key}; add it or a default"]
        rows.append(
            {
                "case_id": str(case.get("case_id")),
                "req_id": str(req),
                "expected": _joined(case.get("expected")),
                "actual": _joined(case.get("actual")),
                "score": case.get("score"),
                "result": case.get("result"),
            }
        )
    provenance = ArtifactImport(
        artifact, source.result_id, source.kind, source.sha256, dict(mapping), len(rows)
    )
    return rows, provenance, []
