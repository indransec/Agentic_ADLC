"""Replay every contract fixture against a freshly seeded simulator (T042, SC-001)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ado_sim import auth
from ado_sim.app import create_app
from ado_sim.db import Database, migrate
from ado_sim.seed import load_seed
from ado_sim.settings import Settings
from tests.conftest import KEY, PROJECT_DIR, SEED
from tests.contract.matching import mismatches

FIXTURES = PROJECT_DIR / "contract" / "fixtures"
OPENAPI = PROJECT_DIR / "contract" / "openapi.json"
FILES = sorted(FIXTURES.glob("*/*.json"))
REQUIRED_REFUSALS = {
    "update/stale_rev": 412,
    "update/unknown_field": 400,
    "get/unknown_item": 404,
    "list/too_many_ids": 400,
    "wiql/unsupported_ever": 400,
    "any/no_token": 401,
    "any/missing_api_version": 400,
    "any/unsupported_operation": 404,
    "any/unknown_project": 404,
}


def _name(path: Path) -> str:
    return f"{path.parent.name}/{path.stem}"


def _load(path: Path) -> dict[str, Any]:
    fixture: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return fixture


@pytest.fixture
def simulator(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str]]]:
    settings = Settings(db_path=tmp_path / "sim.db", token_key=KEY, seed_file=SEED)
    db = Database(settings.db_path, create=True)
    migrate(db)
    load_seed(db, SEED)
    with db.read() as conn:
        names = [row[0] for row in conn.execute("SELECT unique_name FROM identity")]
    tokens = {name: auth.issue(db, KEY, name)[1] for name in names}
    db.close()
    with TestClient(create_app(settings)) as client:
        yield client, tokens


def _send(client: TestClient, tokens: dict[str, str], identity: str | None, request: Any) -> Any:
    headers = dict(request.get("headers", {}))
    if request.get("auth", True):
        assert identity is not None
        headers["Authorization"] = f"Bearer {tokens[identity]}"
    body = json.dumps(request["body"]) if "body" in request else None
    return client.request(
        request["method"], request["path"], params=request["query"], headers=headers, content=body
    )


@pytest.mark.parametrize("path", FILES, ids=_name)
def test_fixture_replays(path: Path, simulator: tuple[TestClient, dict[str, str]]) -> None:
    client, tokens = simulator
    fixture = _load(path)
    assert (fixture["operation"], fixture["case"]) == (path.parent.name, path.stem)
    identity = fixture["identity"]
    for step in fixture["setup"]:
        response = _send(client, tokens, identity, step)
        assert response.status_code == 200, (step["path"], response.text)
    response = _send(client, tokens, identity, fixture["request"])
    expected = fixture["expected"]
    assert response.status_code == expected["status"], response.text
    body = response.json() if response.content else None
    problems = mismatches(expected["body"], body)
    assert not problems, "\n".join(problems)


def test_every_operation_has_a_success_case() -> None:
    served = json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"]
    covered: set[tuple[str, str]] = set()
    for path in FILES:
        fixture = _load(path)
        if fixture["expected"]["status"] == 200:
            request = fixture["request"]
            covered.add((request["method"].lower(), _template_of(request["path"], served)))
    wanted = {
        (method, route)
        for route, operations in served.items()
        if "/_apis/" in route
        for method in operations
    }
    assert wanted - covered == set()


def _template_of(path: str, routes: dict[str, Any]) -> str:
    parts = path.split("?")[0].strip("/").split("/")
    for route in routes:
        template = route.strip("/").split("/")
        if len(template) == len(parts) and all(
            (
                t.startswith("{")
                or (t.startswith("${") and p.startswith("$"))
                or t.lower() == p.lower()
            )
            for t, p in zip(template, parts, strict=True)
        ):
            return route
    return path


def test_required_refusals_are_present() -> None:
    found = {_name(path): _load(path)["expected"]["status"] for path in FILES}
    assert {name: found.get(name) for name in REQUIRED_REFUSALS} == REQUIRED_REFUSALS


def test_no_fixture_holds_a_token() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        assert "Authorization" not in text, path
        assert "Bearer " not in text and "Basic " not in text, path


@pytest.mark.parametrize(
    ("pattern", "value", "ok"),
    [
        ("<int>", 3, True),
        ("<int>", True, False),
        ("<datetime>", "2026-11-20T10:00:00.123456Z", True),
        ("<datetime>", "2026-11-20", False),
        ("<uuid>", "f5621a6e-2b60-5795-84d6-1f4d6067aa07", True),
        ("<url>", "http://h/x", True),
        ("<url>", "h/x", False),
        ([1, "<more>"], [1, 2, 3], True),
        ([1, "<more>"], [], False),
        ([1], [1, 2], False),
        ({"a": 1}, {"a": 1, "b": 2}, False),
        ({"a": "<any>"}, {"a": None}, True),
        (1, 1.0, False),
    ],
)
def test_matching(pattern: Any, value: Any, ok: bool) -> None:
    assert (mismatches(pattern, value) == []) is ok
