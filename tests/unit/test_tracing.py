"""US6: request tracing, health excluded, no credentials, harmless failures (FR-025, FR-026)."""

import logging
from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adlc.api.app import create_app
from adlc.config.settings import Settings
from adlc.identity.hashing import hash_password

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "tracing-test-password"


class FailingExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        raise ConnectionError("collector down")

    def shutdown(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _enable_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)


def _settings(tmp_path: Path) -> Settings:
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text(
        "accounts:\n  - {account_name: owner.business, display_name: O, "
        f"roles: [business_owner], credential_hash: '{hash_password(PASSWORD)}'}}\n"
    )
    return Settings.model_validate(
        {
            "env": "dev",
            "db_host": "127.0.0.1",
            "db_port": 1,
            "db_app_password": "tracing-app-password",
            "session_secret": "tracing-session-secret-" + "t" * 16,
            "accounts_file": accounts,
            "role_catalogue": ROOT / "adlc-specs" / "shared" / "roles.yaml",
        }
    )


def _flush(app: FastAPI) -> None:
    app.state.tracer_provider.force_flush()


def test_request_creates_server_span_without_credentials(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    app = create_app(_settings(tmp_path), span_exporter=exporter)
    with TestClient(app) as client:
        token = client.post(
            "/auth/sign-in", json={"account_name": "owner.business", "password": PASSWORD}
        ).json()["token"]
        _flush(app)
        exporter.clear()
        assert (
            client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        )
    _flush(app)
    spans = exporter.get_finished_spans()
    server = [s for s in spans if s.kind.name == "SERVER"]
    assert len(server) == 1
    assert server[0].resource.attributes["service.name"] == "adlc-api"
    for span in spans:
        for key, value in (span.attributes or {}).items():
            assert "authorization" not in key.lower()
            assert token not in str(value)


def test_health_is_not_traced(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    app = create_app(_settings(tmp_path), span_exporter=exporter)
    with TestClient(app) as client:
        client.get("/health")
    _flush(app)
    assert exporter.get_finished_spans() == ()


def test_exporter_failure_does_not_affect_requests(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    app = create_app(_settings(tmp_path), span_exporter=FailingExporter())
    with TestClient(app) as client:
        response = client.get("/auth/me")
    assert response.status_code == 401  # normal answer, unaffected by tracing
    _flush(app)
    warnings = [
        r for r in caplog.records if r.name == "adlc.tracing" and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
