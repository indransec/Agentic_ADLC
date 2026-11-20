"""A worker sees only its own settings, the trace project and a minimal environment."""

from pathlib import Path

import pytest

from pilot_tools.workers import worker_environment


def test_trace_project_is_passed_on_and_secrets_are_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "openinference.project.name=pilot-triage-dev")
    monkeypatch.setenv("PILOT_OTLP_ENDPOINT", "http://phoenix:6006")
    monkeypatch.setenv("ADLC_DB_PATH", "/var/lib/adlc/db/adlc.db")  # a platform setting
    env = worker_environment(tmp_path, "sha256:" + "a" * 64, "dev", {"model_mode": "simulated"})
    assert env["OTEL_RESOURCE_ATTRIBUTES"] == "openinference.project.name=pilot-triage-dev"
    assert env["PILOT_OTLP_ENDPOINT"] == "http://phoenix:6006"
    assert env["PILOT_ENVIRONMENT"] == "dev" and env["PILOT_MODEL_MODE"] == "simulated"
    assert "ADLC_DB_PATH" not in env
