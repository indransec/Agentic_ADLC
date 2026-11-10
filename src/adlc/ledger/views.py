"""Read views per run and per use case (FR-020 to FR-022; US5).

Features 007 (inbox) and 013 (dashboard) read these; they give references and hashes, never
artifact content. Checklist results come from the reviewer's recommendation (FR-021).
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, text

GENERAL = "general"  # findings not tied to one checklist item


def checklist_rows(recommendation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One row per scored item; a finding ``"<item>: text"`` joins its item, others are general."""
    scores = dict(recommendation.get("checklist_scores") or {})
    findings: dict[str, list[str]] = {}
    for finding in recommendation.get("findings") or []:
        item, sep, rest = str(finding).partition(":")
        key = item.strip() if sep and item.strip() in scores else GENERAL
        findings.setdefault(key, []).append(rest.strip() if key != GENERAL else str(finding))
    rows = [
        {"item_id": item, "score": int(score), "finding": "; ".join(findings.get(item, [])) or None}
        for item, score in scores.items()
    ]
    if GENERAL in findings:
        rows.append({"item_id": GENERAL, "score": None, "finding": "; ".join(findings[GENERAL])})
    return rows


def _rows(conn: Connection, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def run_timeline(conn: Connection, run_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "SELECT step, actor_type, actor_id, started_at, ended_at, duration_seconds, outcome "
        "FROM run.v_run_step WHERE run_id = :r ORDER BY started_at, run_activity_id",
        r=run_id,
    )


def run_checks(conn: Connection, run_id: str) -> list[dict[str, Any]]:
    """Policy decisions of the run. Controls carry the build ``attempt`` they checked (as agent
    versions and checklist results do); a control evaluated again within the same attempt is a
    ``recheck`` after a person's edit. Prerequisites and conditions have no attempt."""
    return _rows(
        conn,
        "SELECT check_id, rule, passed, reason, synthetic, fail_safe, decided_at, attempt, "
        "(attempt IS NOT NULL AND row_number() OVER (PARTITION BY check_id, attempt "
        "ORDER BY policy_decision_id) > 1) AS recheck "
        "FROM run.policy_decision WHERE run_id = :r AND kind = 'evaluate' "
        "ORDER BY policy_decision_id",
        r=run_id,
    )


def checklist_results(conn: Connection, run_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "SELECT attempt, item_id, score, finding, recorded_at FROM run.checklist_result "
        "WHERE run_id = :r ORDER BY checklist_result_id",
        r=run_id,
    )


def artifact_versions(conn: Connection, run_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn,
        "SELECT artifact_id, version, content_hash, producer_type, producer_id, attempt, "
        "derived_from_version, schema_valid, created_at FROM run.artifact_version "
        "WHERE run_id = :r ORDER BY artifact_id, version",
        r=run_id,
    )


def ledger_reference(conn: Connection, run_id: str) -> dict[str, Any] | None:
    rows = _rows(
        conn,
        "SELECT ledger_key, content_hash, previous_record_hash, written_at "
        "FROM ledger.ledger_record WHERE run_id = :r",
        r=run_id,
    )
    return rows[0] if rows else None


def run_view(conn: Connection, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "timeline": run_timeline(conn, run_id),
        "checks": run_checks(conn, run_id),
        "checklist": checklist_results(conn, run_id),
        "artifact_versions": artifact_versions(conn, run_id),
        "ledger_record": ledger_reference(conn, run_id),
    }


def usecase_summary(conn: Connection, usecase_id: str) -> list[dict[str, Any]]:
    rows = _rows(
        conn,
        "SELECT terminal_id, runs, reworks, clarification_rounds, escalations, "
        "automatic_seconds, waiting_seconds FROM run.v_usecase_terminal_summary "
        "WHERE usecase_id = :u ORDER BY terminal_id",
        u=usecase_id,
    )
    for row in rows:
        for key in ("automatic_seconds", "waiting_seconds"):
            row[key] = float(row[key])
        for key in ("runs", "reworks", "clarification_rounds", "escalations"):
            row[key] = int(row[key])
    return rows
