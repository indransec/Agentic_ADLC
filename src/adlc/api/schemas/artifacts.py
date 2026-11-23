"""Answers of the artifact routes: edits, spreadsheet uploads, attachments and history."""

from adlc.api.schemas.base import ApiModel, Record, RunSummary, Timestamp


class ArtifactSaved(ApiModel):
    changed: bool
    run: RunSummary


class RunChanged(ApiModel):
    run: RunSummary


class ArtifactHistoryEntry(ApiModel):
    run_id: str
    artifact_id: str
    version: int
    attempt: int | None
    content_hash: str
    derived_from_version: int | None
    producer_type: str
    producer_id: str
    schema_valid: bool
    created_at: Timestamp
    attachments: list[Record]
