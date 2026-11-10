"""Artifact versions (contracts/artifacts.md; FR-008 to FR-010; research R-04).

Every agent build attempt and every human edit is a numbered version, stored by content hash. The
run's inline artifacts stay as a cache of the latest versions' content.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection

from adlc.ledger import store
from adlc.ledger.storage import FileRef, structured_hash
from adlc.orchestration import spec_view
from adlc.orchestration.tracing import span


@dataclass(frozen=True)
class Producer:
    type: str  # agent | person
    id: str
    attempt: int | None = None


@dataclass(frozen=True)
class NewAttachment:
    ref: FileRef
    file_name: str


@dataclass(frozen=True)
class Change:
    rows: Any
    attachments: Sequence[NewAttachment] = field(default_factory=tuple)


def schema_valid(content: Any, columns: Sequence[str]) -> bool:
    """A table whose every row has every declared column (FR-008)."""
    if not isinstance(content, list) or not all(isinstance(r, Mapping) for r in content):
        return False
    return all(all(c in row for c in columns) for row in content)


def changed(current_hash: str | None, content: Any) -> bool:
    """Content differs when its normal-form hash differs (key order ignored, row order kept)."""
    return current_hash != structured_hash(content)


def record(
    conn: Connection,
    run_id: str,
    spec: Mapping[str, Any],
    changes: Mapping[str, Change],
    producer: Producer,
    put_structured: Any,
) -> dict[str, int]:
    """Write a new version for each artifact whose content changed or that gains attachments.
    Returns ``{artifact_id: new version}``."""
    columns = {a.id: a.columns for a in spec_view.artifacts(spec)}
    current = {v["artifact_id"]: v for v in store.latest_versions(conn, run_id)}
    written: dict[str, int] = {}
    with span("ledger", "record_versions", run_id=run_id):
        for artifact_id, change in changes.items():
            previous = current.get(artifact_id)
            current_hash = None if previous is None else str(previous["content_hash"])
            if not change.attachments and not changed(current_hash, change.rows):
                continue
            digest = put_structured(conn, change.rows)
            version = (previous["version"] if previous else 0) + 1
            store.insert_version(
                conn,
                {
                    "run_id": run_id,
                    "artifact_id": artifact_id,
                    "version": version,
                    "content_hash": digest,
                    "producer_type": producer.type,
                    "producer_id": producer.id,
                    "attempt": producer.attempt,
                    "derived_from_version": previous["version"] if previous else None,
                    "schema_valid": schema_valid(change.rows, columns.get(artifact_id, ())),
                },
            )
            for attachment in change.attachments:
                store.insert_attachment(
                    conn,
                    {
                        "run_id": run_id,
                        "artifact_id": artifact_id,
                        "version": version,
                        "content_hash": attachment.ref.content_hash,
                        "file_name": attachment.file_name,
                        "media_type": attachment.ref.media_type,
                        "size": attachment.ref.size,
                    },
                )
            written[artifact_id] = version
    return written


def ledger_entries(conn: Connection, run_id: str, spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The run's latest versions in spec order, as listed in a version-2 record (FR-001)."""
    latest = {v["artifact_id"]: v for v in store.latest_versions(conn, run_id)}
    order = [a.id for a in spec_view.artifacts(spec)]
    ids = [a for a in order if a in latest] + sorted(set(latest) - set(order))
    entries = []
    for artifact_id in ids:
        v = latest[artifact_id]
        entries.append(
            {
                "id": artifact_id,
                "version": v["version"],
                "content_hash": v["content_hash"],
                "schema_valid": v["schema_valid"],
                "producer": {"type": v["producer_type"], "id": v["producer_id"]},
                "attachments": store.attachments(conn, run_id, artifact_id, v["version"]),
            }
        )
    return entries


def enrich_emitted(
    emitted: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Artifact references in emitted values carry the version and content hash (FR-013)."""
    by_id = {e["id"]: e for e in entries}
    out: dict[str, Any] = {}
    for name, value in emitted.items():
        if isinstance(value, Mapping) and set(value) == {"artifact"} and value["artifact"] in by_id:
            entry = by_id[value["artifact"]]
            out[name] = {
                "artifact": value["artifact"],
                "version": entry["version"],
                "content_hash": entry["content_hash"],
            }
        else:
            out[name] = value
    return out


def current_content(conn: Connection, run_id: str, get_structured: Any) -> dict[str, Any]:
    """The latest versions' content, keyed by artifact id (the run's inline cache)."""
    return {
        v["artifact_id"]: get_structured(conn, v["content_hash"])
        for v in store.latest_versions(conn, run_id)
    }


def history(conn: Connection, run_id: str, artifact_id: str) -> list[dict[str, Any]]:
    out = []
    for v in store.version_history(conn, run_id, artifact_id):
        out.append({**v, "attachments": store.attachments(conn, run_id, artifact_id, v["version"])})
    return out
