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
