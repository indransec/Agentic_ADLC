"""SQL for the evidence ledger tables (data-model.md), on the caller's connection."""

import json
from typing import Any

from sqlalchemy import Connection, text

from adlc.spec_toolkit.normalise import normalise


def insert_blob(conn: Connection, digest: str, value: Any) -> None:
    body = normalise(value)
    conn.execute(
        text(
            "INSERT INTO ledger.content_blob (content_hash, body, size) "
            "VALUES (:h, CAST(:b AS jsonb), :s) ON CONFLICT (content_hash) DO NOTHING"
        ),
        {"h": digest, "b": body, "s": len(body.encode("utf-8"))},
    )


def load_blob(conn: Connection, digest: str) -> Any | None:
    row = conn.execute(
        text("SELECT body FROM ledger.content_blob WHERE content_hash = :h"), {"h": digest}
    ).first()
    return None if row is None else row[0]


def insert_file_object(conn: Connection, digest: str, size: int, media_type: str) -> None:
    conn.execute(
        text(
            "INSERT INTO ledger.file_object (content_hash, size, media_type) VALUES (:h, :s, :m) "
            "ON CONFLICT (content_hash) DO NOTHING"
        ),
        {"h": digest, "s": size, "m": media_type},
    )


def file_object_exists(conn: Connection, digest: str) -> bool:
    return (
        conn.execute(
            text("SELECT 1 FROM ledger.file_object WHERE content_hash = :h"), {"h": digest}
        ).first()
        is not None
    )


def as_json(value: Any) -> str:
    return json.dumps(value, default=str)


# ------------------------------------------------------------------ artifact versions


def latest_versions(conn: Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT DISTINCT ON (artifact_id) run_id, artifact_id, version, content_hash, "
            "producer_type, producer_id, attempt, derived_from_version, schema_valid, created_at "
            "FROM run.artifact_version WHERE run_id = :r ORDER BY artifact_id, version DESC"
        ),
        {"r": run_id},
    ).mappings()
    return [dict(r) for r in rows]


def version_history(conn: Connection, run_id: str, artifact_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT run_id, artifact_id, version, content_hash, producer_type, producer_id, "
            "attempt, derived_from_version, schema_valid, created_at FROM run.artifact_version "
            "WHERE run_id = :r AND artifact_id = :a ORDER BY version"
        ),
        {"r": run_id, "a": artifact_id},
    ).mappings()
    return [dict(r) for r in rows]


def insert_version(conn: Connection, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO run.artifact_version (run_id, artifact_id, version, content_hash, "
            "producer_type, producer_id, attempt, derived_from_version, schema_valid) VALUES "
            "(:run_id, :artifact_id, :version, :content_hash, :producer_type, :producer_id, "
            ":attempt, :derived_from_version, :schema_valid)"
        ),
        row,
    )


def attachments(
    conn: Connection, run_id: str, artifact_id: str, version: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT content_hash, file_name AS name, media_type, size "
            "FROM run.artifact_attachment WHERE run_id = :r AND artifact_id = :a "
            "AND version = :v ORDER BY file_name, content_hash"
        ),
        {"r": run_id, "a": artifact_id, "v": version},
    ).mappings()
    return [dict(r) for r in rows]


def insert_attachment(conn: Connection, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO run.artifact_attachment (run_id, artifact_id, version, content_hash, "
            "file_name, media_type, size) VALUES (:run_id, :artifact_id, :version, :content_hash, "
            ":file_name, :media_type, :size)"
        ),
        row,
    )


def insert_checklist_results(
    conn: Connection, run_id: str, attempt: int, rows: list[dict[str, Any]]
) -> None:
    for row in rows:
        conn.execute(
            text(
                "INSERT INTO run.checklist_result (run_id, attempt, item_id, score, finding) "
                "VALUES (:r, :a, :item_id, :score, :finding)"
            ),
            {"r": run_id, "a": attempt, **row},
        )
