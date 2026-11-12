"""Evidence from the tool results the platform recorded (feature 011, research R-05,
contracts/evidence-sources.md): ``ci``, ``sbom``, ``harness``, ``redteam`` and ``dlp``.

The candidate package is the one the MCP registry's ``bound_values.candidate_hash`` reference
names (the terminal and artifact are spec content, never code). A source with no recorded result
is "not available", so the composite provider falls back to synthetic evidence, labelled.
"""

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import Connection, text

SOURCES = ("ci", "sbom", "harness", "redteam", "dlp")
HASH_FIELDS = ("sha256", "package_hash", "hash")
SHA = "sha256:"


def hashes(value: Any) -> list[str]:
    found = []
    for row in value if isinstance(value, list) else [value]:
        if isinstance(row, Mapping):
            for name in HASH_FIELDS:
                if str(row.get(name) or "").startswith(SHA):
                    found.append(str(row[name]))
                    break
    return found


def _latest(
    conn: Connection,
    usecase_id: str,
    kind: str,
    *,
    run_id: str | None = None,
    package: str | None = None,
) -> tuple[int, dict[str, Any]] | None:
    row = conn.execute(
        text(
            "SELECT tool_result_id, result FROM tools.tool_result WHERE usecase_id = :u "
            "AND kind = :k AND (CAST(:r AS text) IS NULL OR run_id = :r) "
            "AND (CAST(:p AS text) IS NULL OR package_hash = :p) "
            "ORDER BY tool_result_id DESC LIMIT 1"
        ),
        {"u": usecase_id, "k": kind, "r": run_id, "p": package},
    ).first()
    return None if row is None else (int(row[0]), dict(row[1]))


def _ci(conn: Connection, usecase_id: str, run_id: str | None) -> tuple[int, dict[str, Any]] | None:
    return _latest(conn, usecase_id, "ci", run_id=run_id) or _latest(conn, usecase_id, "ci")


def read(
    conn: Connection,
    source: str,
    usecase_id: str,
    run_id: str | None,
    candidate: Callable[[], str | None],
) -> dict[str, Any] | None:
    """The source's value, or ``None`` when nothing was recorded for it."""
    if source in ("ci", "sbom"):
        found = _ci(conn, usecase_id, run_id)
        if found is None:
            return None
        result_id, result = found
        if source == "sbom":
            sbom = result.get("sbom") or {}
            return {
                "generated": bool(sbom.get("generated")),
                "licences_approved": bool(sbom.get("licences_approved")),
            }
        checks = result.get("checks") or []
        green = bool(checks) and all(c.get("passed") for c in checks) and result.get("package_hash")
        return {
            "status": "green" if green else "red",
            "run_id": f"RES-{result_id}",
            "package_hash": result.get("package_hash"),
            "tests": dict(result.get("tests") or {}),
            "scans": dict(result.get("scans") or {}),
            "observability": {
                str(o.get("signal")): {"emitting": bool(o.get("emitting"))}
                for o in result.get("observability") or []
            },
        }
    package = candidate()
    if package is None:
        return None
    found = _latest(conn, usecase_id, source, package=package)
    if found is None:
        return None
    result_id, result = found
    if source == "harness":
        return {
            "metrics": dict(result.get("catalogue") or {}),
            "calibration": dict(result.get("calibration") or {}),
            "dataset": dict(result.get("dataset") or {}),
            "result_id": f"RES-{result_id}",
        }
    if source == "redteam":
        return {
            str(entry["evidence_metric"]): entry.get("rate")
            for entry in (result.get("by_category") or {}).values()
            if entry.get("evidence_metric")
        }
    return {"pii_leak_count": int(result.get("leaking_answers") or 0)}
