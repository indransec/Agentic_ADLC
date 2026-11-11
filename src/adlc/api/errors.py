"""One error shape for every platform operation (007 research R-05, FR-021).

The body is always ``{"kind": ..., "detail": ...}`` (with ``field`` for invalid input). A stack
trace or request body is never returned.
"""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from adlc.ledger.service import UnknownArtifact
from adlc.ledger.spreadsheet import InvalidUpload
from adlc.ledger.storage import AttachmentRefused
from adlc.orchestration.engine import StaleRun, UnknownRun
from adlc.orchestration.service import (
    AlreadyAnswered,
    InvalidDecision,
    NoActiveSpecs,
    NotAuthorised,
    NotDeadLettered,
    UnknownEvent,
)
from adlc.orchestration.states import InvalidTransition


class NotFound(Exception):
    """A use case, run, waiver, clarification, event or file that does not exist (or is not
    reachable through the path given)."""


class Invalid(Exception):
    def __init__(self, detail: str, field: str | None = None) -> None:
        super().__init__(detail)
        self.field = field


ERRORS: Sequence[tuple[tuple[type[Exception], ...], int, str]] = (
    ((NotAuthorised,), 403, "not_allowed"),
    ((NotFound, UnknownRun, UnknownEvent, NotDeadLettered), 404, "not_found"),
    ((StaleRun,), 409, "stale"),
    ((InvalidTransition, AlreadyAnswered, NoActiveSpecs), 409, "wrong_state"),
    ((Invalid, InvalidDecision, InvalidUpload, AttachmentRefused, UnknownArtifact), 422, "invalid"),
)


def body(kind: str, detail: str, field: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": kind, "detail": detail[:500]}
    if field:
        out["field"] = field
    return out


def install_errors(app: FastAPI) -> None:
    for types, status, kind in ERRORS:
        for exc_type in types:
            app.add_exception_handler(exc_type, _handler(status, kind))
    app.add_exception_handler(RequestValidationError, _validation)


def _handler(status: int, kind: str) -> Any:
    async def handle(request: Request, exc: Exception) -> JSONResponse:
        field = exc.field if isinstance(exc, Invalid) else None
        return JSONResponse(body(kind, str(exc) or kind, field), status_code=status)

    return handle


async def _validation(request: Request, exc: Exception) -> JSONResponse:
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    first = errors[0] if errors else {}
    loc = [str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path")]
    message = str(first.get("msg", "invalid input"))
    return JSONResponse(body("invalid", message, ".".join(loc) or None), status_code=422)
