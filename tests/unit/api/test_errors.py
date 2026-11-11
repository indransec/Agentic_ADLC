"""T005: one error shape, mapped from the service exceptions (research R-05)."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from adlc.api.errors import Invalid, NotFound, install_errors
from adlc.ledger.service import UnknownArtifact
from adlc.ledger.spreadsheet import InvalidUpload
from adlc.ledger.storage import AttachmentRefused
from adlc.orchestration.engine import StaleRun, UnknownRun
from adlc.orchestration.service import AlreadyAnswered, InvalidDecision, NotAuthorised
from adlc.orchestration.states import InvalidTransition

CASES: list[tuple[Exception, int, str]] = [
    (NotAuthorised("needs product_owner"), 403, "not_allowed"),
    (UnknownRun("UC-1/T1/run-9"), 404, "not_found"),
    (NotFound("no such waiver"), 404, "not_found"),
    (StaleRun("at version 7"), 409, "stale"),
    (InvalidTransition("decide is not allowed in state closed"), 409, "wrong_state"),
    (AlreadyAnswered("c-1"), 409, "wrong_state"),
    (InvalidDecision("a reason is required"), 422, "invalid"),
    (InvalidUpload("no sheet fits"), 422, "invalid"),
    (AttachmentRefused("type not allowed"), 422, "invalid"),
    (UnknownArtifact("x is not an artifact"), 422, "invalid"),
]


class Body(BaseModel):
    name: str


def _app(raised: Exception) -> TestClient:
    app = FastAPI()
    install_errors(app)

    @app.get("/boom")
    def boom() -> None:
        raise raised

    @app.post("/body")
    def post(body: Body) -> dict[str, Any]:
        return {}

    @app.get("/field")
    def field() -> None:
        raise Invalid("comment is required for rework", field="comment")

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("exc", "status", "kind"), CASES, ids=lambda c: type(c).__name__)
def test_mapping(exc: Exception, status: int, kind: str) -> None:
    response = _app(exc).get("/boom")
    assert response.status_code == status
    assert response.json() == {"kind": kind, "detail": str(exc)}


def test_validation_and_field() -> None:
    client = _app(RuntimeError())
    bad = client.post("/body", json={"name": 1, "secret": "x" * 100})
    assert bad.status_code == 422 and bad.json()["kind"] == "invalid"
    assert bad.json()["field"] == "name" and "x" * 100 not in bad.text
    assert client.get("/field").json() == {
        "kind": "invalid",
        "detail": "comment is required for rework",
        "field": "comment",
    }


def test_unexpected_errors_never_leak_a_trace() -> None:
    response = _app(RuntimeError("database password is hunter2")).get("/boom")
    assert response.status_code == 500 and "hunter2" not in response.text
