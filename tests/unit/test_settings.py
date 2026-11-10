"""US3: settings fail fast with named, value-free errors (FR-013 to FR-015, SC-005)."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from adlc.config.errors import format_settings_error
from adlc.config.settings import Settings

APP_PW = "app-password-value-0001"
SESSION = "session-secret-value-0000000000000001"
REQUIRED = (
    "ADLC_ENV",
    "ADLC_DB_HOST",
    "ADLC_DB_APP_PASSWORD",
    "ADLC_SESSION_SECRET",
    "ADLC_ACCOUNTS_FILE",
)


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    accounts = tmp_path / "accounts.yaml"
    accounts.write_text("accounts: []\n")
    for key in list(os.environ):
        if key.startswith("ADLC_"):
            monkeypatch.delenv(key)
    env = {
        "ADLC_ENV": "dev",
        "ADLC_DB_HOST": "localhost",
        "ADLC_DB_APP_PASSWORD": APP_PW,
        "ADLC_SESSION_SECRET": SESSION,
        "ADLC_ACCOUNTS_FILE": str(accounts),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


def _error() -> str:
    try:
        Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        return format_settings_error(exc, Settings)
    raise AssertionError("expected a validation error")


def test_valid_settings_load(valid_env: dict[str, str]) -> None:
    settings = Settings()  # type: ignore[call-arg]
    assert settings.env == "dev"
    assert settings.session_ttl.total_seconds() == 8 * 3600
    assert settings.db_port == 5432


@pytest.mark.parametrize("name", REQUIRED)
def test_missing_required_setting_is_named(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(name)
    output = _error()
    assert output.startswith("adlc: configuration error\n")
    assert f"  {name}: missing; expected " in output


@pytest.mark.parametrize("name", REQUIRED)
def test_empty_value_counts_as_missing(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "")
    assert f"  {name}: missing;" in _error()


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("ADLC_DB_PORT", "abc", "ADLC_DB_PORT: invalid; expected integer 1-65535"),
        ("ADLC_DB_PORT", "70000", "ADLC_DB_PORT: invalid; expected integer 1-65535"),
        ("ADLC_ENV", "prod", "ADLC_ENV: invalid; expected dev or demo"),
        (
            "ADLC_SESSION_SECRET",
            "short",
            "ADLC_SESSION_SECRET: invalid; expected at least 32 characters (secret)",
        ),
        ("ADLC_SESSION_TTL", "5m", "ADLC_SESSION_TTL: invalid; expected <int><unit>"),
        (
            "ADLC_ACCOUNTS_FILE",
            "/does/not/exist.yaml",
            "ADLC_ACCOUNTS_FILE: invalid; expected path to a readable file",
        ),
    ],
)
def test_invalid_setting_names_expected_form(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, name: str, value: str, expected: str
) -> None:
    monkeypatch.setenv(name, value)
    assert expected in _error()


def test_error_output_never_contains_values(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADLC_SESSION_SECRET", "tiny-secret-value")
    monkeypatch.setenv("ADLC_DB_PORT", "port-value-xyz")
    monkeypatch.setenv("ADLC_ENV", "env-value-xyz")
    output = _error()
    for value in ("tiny-secret-value", "port-value-xyz", "env-value-xyz", APP_PW):
        assert value not in output


def test_repr_and_dump_hide_secrets(valid_env: dict[str, str]) -> None:
    settings = Settings()  # type: ignore[call-arg]
    for text in (repr(settings), str(settings), settings.model_dump_json()):
        assert APP_PW not in text
        assert SESSION not in text


# ---------------------------------------------------------------- 003 orchestrator settings


@pytest.fixture
def orchestrator_env(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADLC_SESSION_SECRET")
    monkeypatch.delenv("ADLC_ACCOUNTS_FILE")
    monkeypatch.setenv("ADLC_DEADLETTER_ROLE", "adlc_coe")


def _orchestrator_error() -> str:
    from adlc.config.settings import OrchestratorSettings

    try:
        OrchestratorSettings()  # type: ignore[call-arg]
    except ValidationError as exc:
        return format_settings_error(exc, OrchestratorSettings)
    raise AssertionError("expected a validation error")


def test_orchestrator_defaults(orchestrator_env: None) -> None:
    from datetime import timedelta

    from adlc.config.settings import OrchestratorSettings

    s = OrchestratorSettings()  # type: ignore[call-arg]
    assert s.time_scale == 1.0
    assert s.poll_interval == timedelta(seconds=1)
    assert s.lease == timedelta(minutes=5)
    assert s.deadletter_role == "adlc_coe"  # from the environment: no role names in code
    assert s.heartbeat_max_age == timedelta(seconds=30)


def test_orchestrator_needs_deadletter_role(
    orchestrator_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ADLC_DEADLETTER_ROLE")
    assert "ADLC_DEADLETTER_ROLE" in _orchestrator_error()


def test_orchestrator_needs_no_session_or_accounts(orchestrator_env: None) -> None:
    from adlc.config.settings import OrchestratorSettings

    assert OrchestratorSettings().db_app_password.get_secret_value() == APP_PW  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ADLC_TIME_SCALE", "0"),
        ("ADLC_TIME_SCALE", "-1"),
        ("ADLC_TIME_SCALE", "fast"),
        ("ADLC_POLL_INTERVAL", "1m"),
        ("ADLC_LEASE", "soon"),
        ("ADLC_HEARTBEAT_MAX_AGE", "30"),
        ("ADLC_DEADLETTER_ROLE", "no_such_role"),
    ],
)
def test_orchestrator_invalid_values_name_the_setting(
    orchestrator_env: None, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    message = _orchestrator_error()
    assert name in message
    if len(value) > 3:  # short numbers can appear in the expected form ("greater than zero")
        assert value not in message.replace(name, "")


def test_orchestrator_synthetic_dir_and_accounts(
    orchestrator_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from adlc.config.settings import OrchestratorSettings

    s = OrchestratorSettings()  # type: ignore[call-arg]
    assert s.synthetic_dir == Path("data/synthetic")
    assert s.accounts_file is None
    monkeypatch.setenv("ADLC_SYNTHETIC_DIR", "off")
    accounts = tmp_path / "a.yaml"
    accounts.write_text("accounts: []\n")
    monkeypatch.setenv("ADLC_ACCOUNTS_FILE", str(accounts))
    s = OrchestratorSettings()  # type: ignore[call-arg]
    assert s.synthetic_dir is None
    assert s.accounts_file == accounts


# ---------------------------------------------------------------- 005 ledger settings


def test_file_store_defaults(valid_env: dict[str, str]) -> None:
    s = Settings()  # type: ignore[call-arg]
    assert s.file_store_dir == Path("data/files")
    assert s.attachment_max == 25_000_000
    assert "application/pdf" in s.attachment_types
    assert "application/vnd.ms-excel.sheet.macroEnabled.12" not in s.attachment_types
    assert len(s.attachment_types) == 7


@pytest.mark.parametrize(
    ("value", "expected"), [("25MB", 25_000_000), ("1MB", 1_000_000), ("500", 500), ("2kB", 2_000)]
)
def test_attachment_max_forms(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, value: str, expected: int
) -> None:
    monkeypatch.setenv("ADLC_ATTACHMENT_MAX", value)
    assert Settings().attachment_max == expected  # type: ignore[call-arg]


def test_attachment_max_invalid(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADLC_ATTACHMENT_MAX", "lots")
    assert "ADLC_ATTACHMENT_MAX" in _error()


def test_attachment_types_list(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADLC_ATTACHMENT_TYPES", "application/pdf, text/plain")
    assert Settings().attachment_types == frozenset({"application/pdf", "text/plain"})  # type: ignore[call-arg]
