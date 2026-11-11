"""Artifact edits, spreadsheets, attachments, history and downloads (007 FR-012, FR-013).

Every change carries the run version the person saw (FR-011). Attachments are served as downloads
only, and only for the run named in the path (research R-06).
"""

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from adlc.api.deps import ActorDep, ServicesDep, traced
from adlc.api.errors import Invalid, NotFound
from adlc.inbox.service import run_summary

router = APIRouter(prefix="/runs")

DOWNLOAD_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}
FALLBACK_TYPE = "application/octet-stream"


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: Any
    expected_version: int = Field(ge=0)


VersionField = Annotated[int, Form(ge=0)]


def _read(upload: UploadFile, limit: int) -> bytes:
    """At most ``limit`` bytes; a larger file is refused before it is read in full."""
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise Invalid(f"the file is larger than {limit} bytes", field="file")
    return data


@router.put("/{run_id:path}/artifacts/{artifact_id}")
def edit(
    run_id: str, artifact_id: str, body: Edit, actor: ActorDep, services: ServicesDep
) -> dict[str, Any]:
    traced(run_id=run_id)
    run = services.ledger.edit_artifact(
        actor, run_id, artifact_id, body.rows, expected_version=body.expected_version
    )
    return {"changed": run.version != body.expected_version, "run": run_summary(run)}


@router.post("/{run_id:path}/artifacts/{artifact_id}/spreadsheet")
def spreadsheet(
    run_id: str,
    artifact_id: str,
    file: UploadFile,
    expected_version: VersionField,
    actor: ActorDep,
    services: ServicesDep,
) -> dict[str, Any]:
    traced(run_id=run_id)
    data = _read(file, services.settings.attachment_max)
    run = services.ledger.upload_spreadsheet(
        actor, run_id, artifact_id, data, file.filename or "upload.xlsx", expected_version
    )
    return {"run": run_summary(run)}


@router.post("/{run_id:path}/artifacts/{artifact_id}/attachments")
def attach(
    run_id: str,
    artifact_id: str,
    file: UploadFile,
    expected_version: VersionField,
    actor: ActorDep,
    services: ServicesDep,
) -> dict[str, Any]:
    traced(run_id=run_id)
    data = _read(file, services.settings.attachment_max)
    run = services.ledger.attach_file(
        actor,
        run_id,
        artifact_id,
        data,
        file.filename or "attachment",
        file.content_type or FALLBACK_TYPE,
        expected_version,
    )
    return {"run": run_summary(run)}


@router.get("/{run_id:path}/artifacts/{artifact_id}/history")
def history(
    run_id: str, artifact_id: str, actor: ActorDep, services: ServicesDep
) -> list[dict[str, Any]]:
    traced(run_id=run_id)
    if services.orchestration.get_run(run_id) is None:
        raise NotFound(f"no run {run_id}")
    return services.ledger.artifact_history(run_id, artifact_id)


@router.get("/{run_id:path}/attachments/{content_hash}")
def download(run_id: str, content_hash: str, actor: ActorDep, services: ServicesDep) -> Response:
    traced(run_id=run_id)
    found = services.inbox.attachment(run_id, content_hash)
    data = services.ledger.open_attachment(content_hash) if found else None
    if found is None or data is None:
        raise NotFound(f"no attachment {content_hash} on {run_id}")
    name, media_type = found
    headers = {
        **DOWNLOAD_HEADERS,
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
    }
    return Response(content=data, media_type=media_type, headers=headers)
