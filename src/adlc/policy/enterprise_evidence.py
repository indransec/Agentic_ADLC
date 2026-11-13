"""Evidence from the enterprise mocks' records (feature 012, research R-04,
contracts/telemetry-evidence.md): ``change``, ``release`` and ``retirement``.

The records are the ones the agents' tools wrote (feature 010, ``tools.enterprise_record``, the
latest version of each). The release package is the one the MCP registry's
``bound_values.authorised_hash`` reference names (spec content, never code). A source with no
record is "not available", so the composite provider falls back to synthetic evidence, labelled.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import Connection, text

SOURCES = ("change", "release", "retirement")
REVOKED = ("identity", "tool_scopes")
DISPOSED = "disposed"


def _records(
    conn: Connection, system: str, kind: str, usecase_id: str | None
) -> list[dict[str, Any]]:
    """Current records of a system and kind (one use case, or all), oldest id first."""
    rows = conn.execute(
        text(
            "SELECT DISTINCT ON (record_id) record_id, usecase_id, body "
            "FROM tools.enterprise_record WHERE system = :s AND kind = :k "
            "AND (CAST(:u AS text) IS NULL OR usecase_id = :u) "
            "ORDER BY record_id, version DESC"
        ),
        {"s": system, "k": kind, "u": usecase_id},
    ).mappings()
    found = [{**dict(r["body"]), "id": r["record_id"], "usecase_id": r["usecase_id"]} for r in rows]
    return sorted(found, key=lambda r: int(str(r["id"]).rpartition("-")[2] or 0))


def _change(conn: Connection, usecase_id: str) -> dict[str, Any] | None:
    found = _records(conn, "servicenow", "change", usecase_id)
    if not found:
        return None
    latest = found[-1]
    return {
        "change_id": latest["id"],
        "window": {"start": latest.get("window_start"), "end": latest.get("window_end")},
        "window_requested": bool(latest.get("window_start") and latest.get("window_end")),
        "request_status": str(latest.get("state") or ""),
    }


def _release(
    conn: Connection, usecase_id: str, authorised: Callable[[], str | None]
) -> dict[str, Any] | None:
    """A release exists once its change is raised: the date is the window's start."""
    change = _change(conn, usecase_id)
    start = str((change or {}).get("window", {}).get("start") or "")
    if not start:
        return None
    found: dict[str, Any] = {"release_date": start[:10]}
    package = authorised()
    if package:
        found["package_sha256"] = package
    return found


def _retirement(conn: Connection, usecase_id: str) -> dict[str, Any] | None:
    revoked = {str(r.get("what")) for r in _records(conn, "iam", "revocation", usecase_id)}
    items = _records(conn, "cmdb", "ci", usecase_id)
    agents = {str(a["id"]) for a in _records(conn, "agent_registry", "agent", usecase_id)}
    if not (revoked or items or agents):
        return None
    dependants = [
        a
        for a in _records(conn, "agent_registry", "agent", None)
        if a["usecase_id"] != usecase_id
        and agents & {d.strip() for d in str(a.get("depends_on") or "").split(",")}
        and not str(a.get("owner") or "").strip()
    ]
    return {
        "credentials_revoked": set(REVOKED) <= revoked,
        "data_disposed": bool(items) and all(i.get("data_status") == DISPOSED for i in items),
        "unowned_dependants": len(dependants),
    }


def read(
    conn: Connection, source: str, usecase_id: str, authorised: Callable[[], str | None]
) -> dict[str, Any] | None:
    """The source's value, or ``None`` when nothing was recorded for it."""
    if source == "change":
        return _change(conn, usecase_id)
    if source == "release":
        return _release(conn, usecase_id, authorised)
    if source == "retirement":
        return _retirement(conn, usecase_id)
    return None
