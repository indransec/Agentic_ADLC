"""Shared fixtures: a migrated and seeded database, the store, an API client with tokens."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ado_sim import auth
from ado_sim.app import create_app
from ado_sim.db import Database, migrate
from ado_sim.process import Identity, identity_by_name
from ado_sim.seed import load_seed
from ado_sim.settings import Settings
from ado_sim.workitems import WorkItemStore

PROJECT_DIR = Path(__file__).resolve().parents[1]
SEED = PROJECT_DIR / "seed" / "demo.yaml"
KEY = "test-token-key-" + "k" * 32
ORG = "adlc-demo"
PROJECT = "Agentic ADLC"
WIT = f"/{ORG}/Agentic%20ADLC/_apis/wit"
SERVICE = "adlc-platform@adlc.demo"
OWNER = "product.owner@adlc.demo"
LEAD = "engineering.lead@adlc.demo"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(db_path=tmp_path / "sim.db", token_key=KEY, seed_file=SEED)


@pytest.fixture
def db(settings: Settings) -> Iterator[Database]:
    database = Database(settings.db_path, create=True)
    migrate(database)
    load_seed(database, SEED)
    yield database
    database.close()


@pytest.fixture
def store(db: Database) -> WorkItemStore:
    return WorkItemStore(db)


@dataclass
class People:
    service: Identity
    owner: Identity
    lead: Identity


@pytest.fixture
def people(db: Database) -> People:
    with db.read() as conn:
        found = [identity_by_name(conn, name) for name in (SERVICE, OWNER, LEAD)]
    service, owner, lead = (identity for identity in found if identity is not None)
    return People(service, owner, lead)


def add(path: str, value: Any) -> dict[str, Any]:
    return {"op": "add", "path": path, "value": value}


def title(text: str) -> dict[str, Any]:
    return add("/fields/System.Title", text)


class ApiClient:
    """A test client that calls the API as one of the seeded identities."""

    def __init__(self, client: TestClient, tokens: dict[str, str]):
        self.http = client
        self.tokens = tokens

    def headers(self, user: str | None, content_type: str | None = None) -> dict[str, str]:
        headers = {}
        if user is not None:
            headers["Authorization"] = f"Bearer {self.tokens[user]}"
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def call(
        self,
        method: str,
        path: str,
        *,
        user: str | None = SERVICE,
        params: dict[str, Any] | None = None,
        body: Any = None,
        api_version: str | None = "7.1",
        content_type: str | None = None,
    ) -> Any:
        query = dict(params or {})
        if api_version is not None:
            query.setdefault("api-version", api_version)
        if body is not None and content_type is None:
            content_type = "application/json"
        import json as _json

        return self.http.request(
            method,
            path,
            params=query,
            headers=self.headers(user, content_type),
            content=_json.dumps(body) if body is not None else None,
        )

    def create(self, kind: str, operations: list[dict[str, Any]], user: str = SERVICE) -> Any:
        return self.call(
            "POST",
            f"{WIT}/workitems/${kind}",
            user=user,
            body=operations,
            content_type="application/json-patch+json",
        )

    def patch(
        self, item_id: int, operations: list[dict[str, Any]], user: str = SERVICE, **params: Any
    ) -> Any:
        return self.call(
            "PATCH",
            f"{WIT}/workitems/{item_id}",
            user=user,
            body=operations,
            params=params,
            content_type="application/json-patch+json",
        )

    def new(
        self, kind: str = "Task", name: str = "item", user: str = SERVICE, **fields: Any
    ) -> int:
        operations = [title(name)] + [add(f"/fields/{k}", v) for k, v in fields.items()]
        response = self.create(kind, operations, user)
        assert response.status_code == 200, response.text
        return int(response.json()["id"])


@pytest.fixture
def api(settings: Settings, db: Database) -> Iterator[ApiClient]:
    tokens = {name: auth.issue(db, KEY, name)[1] for name in (SERVICE, OWNER, LEAD)}
    app = create_app(settings)
    with TestClient(app) as client:
        yield ApiClient(client, tokens)
