from pathlib import Path

import pytest

from ado_sim.settings import SettingsError, load_settings, parse_duration

KEY = "k" * 32


def test_defaults() -> None:
    settings = load_settings({"ADO_SIM_DB_PATH": "x.db", "ADO_SIM_TOKEN_KEY": KEY})
    assert settings.db_path == Path("x.db")
    assert settings.port == 8600
    assert settings.host == "127.0.0.1"
    assert settings.seed_file == Path("seed/demo.yaml")
    assert settings.busy_timeout_seconds == 30.0
    assert settings.log_level == "INFO"
    assert settings.otlp_endpoint is None


def test_all_values() -> None:
    settings = load_settings(
        {
            "ADO_SIM_DB_PATH": "a.db",
            "ADO_SIM_TOKEN_KEY": KEY,
            "ADO_SIM_HOST": "10.1.2.3",
            "ADO_SIM_PORT": "9000",
            "ADO_SIM_SEED_FILE": "s.yaml",
            "ADO_SIM_BUSY_TIMEOUT": "500ms",
            "ADO_SIM_LOG_LEVEL": "debug",
            "ADO_SIM_OTLP_ENDPOINT": "http://phoenix:6006",
        }
    )
    assert (settings.host, settings.port, settings.log_level) == ("10.1.2.3", 9000, "DEBUG")
    assert settings.busy_timeout_seconds == 0.5
    assert settings.otlp_endpoint == "http://phoenix:6006"


def test_key_never_in_repr() -> None:
    settings = load_settings({"ADO_SIM_DB_PATH": "a.db", "ADO_SIM_TOKEN_KEY": KEY})
    assert KEY not in repr(settings)


@pytest.mark.parametrize(
    ("env", "name"),
    [
        ({"ADO_SIM_TOKEN_KEY": KEY}, "ADO_SIM_DB_PATH"),
        ({"ADO_SIM_DB_PATH": "a.db"}, "ADO_SIM_TOKEN_KEY"),
        (
            {"ADO_SIM_DB_PATH": "a.db", "ADO_SIM_TOKEN_KEY": "short-secret-value"},
            "ADO_SIM_TOKEN_KEY",
        ),
        (
            {"ADO_SIM_DB_PATH": "a.db", "ADO_SIM_TOKEN_KEY": KEY, "ADO_SIM_PORT": "x"},
            "ADO_SIM_PORT",
        ),
        (
            {"ADO_SIM_DB_PATH": "a.db", "ADO_SIM_TOKEN_KEY": KEY, "ADO_SIM_PORT": "70000"},
            "ADO_SIM_PORT",
        ),
        (
            {"ADO_SIM_DB_PATH": "a.db", "ADO_SIM_TOKEN_KEY": KEY, "ADO_SIM_LOG_LEVEL": "LOUD"},
            "ADO_SIM_LOG_LEVEL",
        ),
        (
            {"ADO_SIM_DB_PATH": "a.db", "ADO_SIM_TOKEN_KEY": KEY, "ADO_SIM_BUSY_TIMEOUT": "45"},
            "ADO_SIM_BUSY_TIMEOUT",
        ),
    ],
)
def test_refusals_name_the_variable_not_the_value(env: dict[str, str], name: str) -> None:
    with pytest.raises(SettingsError) as raised:
        load_settings(env)
    assert name in str(raised.value)
    for value in env.values():
        if value not in ("a.db",):
            assert value not in str(raised.value)


def test_duration_units() -> None:
    assert parse_duration("X", "2m") == 120.0
    assert parse_duration("X", "15s") == 15.0
