"""The platform API over an orchestration harness (007): one account per role, signed-in clients.

Account names match ``tests.support.orchestration.person`` (``<role>-person``), so decisions taken
through the API and through the harness are attributed the same way.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SpanExporter

from adlc.api.app import create_app
from adlc.identity.catalogue import load_role_ids
from adlc.identity.hashing import hash_password
from tests.integration.conftest import settings_for
from tests.support.orchestration import DEADLETTER_ROLE, SPECS, SYNTHETIC, Harness

PASSWORD = "api-test-password-0001"
ROLES = SPECS / "shared" / "roles.yaml"


@cache
def _hash() -> str:
    return hash_password(PASSWORD)  # slow on purpose; computed once


def write_accounts(path: Path) -> Path:
    lines = ["accounts:"]
    for role in sorted(load_role_ids(ROLES)):
        lines += [
            f"  - account_name: {role}-person",
            f"    display_name: {role.replace('_', ' ').title()}",
            f"    roles: [{role}]",
            f"    credential_hash: '{_hash()}'",
        ]
    path.write_text("\n".join(lines) + "\n")
    return path


@dataclass
class Api:
    app: FastAPI
    client: TestClient
    tokens: dict[str, str] = field(default_factory=dict)

    def token(self, role: str) -> str:
        if role not in self.tokens:
            answer = self.client.post(
                "/auth/sign-in", json={"account_name": f"{role}-person", "password": PASSWORD}
            )
            assert answer.status_code == 200, answer.text
            self.tokens[role] = answer.json()["token"]
        return self.tokens[role]

    def as_(self, role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(role)}"}

    def get(self, role: str, path: str, **kw: Any) -> Any:
        return self.client.get(path, headers=self.as_(role), **kw)

    def post(self, role: str, path: str, **kw: Any) -> Any:
        return self.client.post(path, headers=self.as_(role), **kw)

    def put(self, role: str, path: str, **kw: Any) -> Any:
        return self.client.put(path, headers=self.as_(role), **kw)


@contextmanager
def api_for(
    h: Harness,
    tmp_path: Path,
    span_exporter: SpanExporter | None = None,
    **overrides: object,
) -> Iterator[Api]:
    accounts = write_accounts(tmp_path / "accounts.yaml")
    settings = settings_for(
        h.db,
        accounts,
        deadletter_role=DEADLETTER_ROLE,
        synthetic_dir=SYNTHETIC,
        spec_dir=SPECS,
        file_store_dir=tmp_path / "files",
        db_name=h.db.name,  # the harness's per-test database
        **overrides,
    )
    app = create_app(settings, span_exporter)
    app.state.services.clock = h.clock  # one clock for the API and the harness worker
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Api(app, client)
    app.state.engine.dispose()
