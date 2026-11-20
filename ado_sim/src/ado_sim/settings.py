"""Settings from the environment, prefix ``ADO_SIM_`` (contracts/cli-settings-seed.md)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

MIN_TOKEN_KEY_LENGTH = 32
_DURATION = re.compile(r"^(\d+)(ms|s|m)$")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class SettingsError(ValueError):
    """A setting is missing or invalid. The message names the variable, never its value."""


@dataclass(frozen=True)
class Settings:
    db_path: Path
    token_key: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 8600
    seed_file: Path = Path("seed/demo.yaml")
    busy_timeout_seconds: float = 30.0
    log_level: str = "INFO"
    otlp_endpoint: str | None = None


def parse_duration(name: str, raw: str) -> float:
    match = _DURATION.match(raw.strip())
    if not match:
        raise SettingsError(f"{name} must be <integer><unit> with unit ms, s or m (e.g. 30s)")
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env

    def get(name: str) -> str | None:
        value = source.get(name)
        return value if value not in (None, "") else None

    db_path = get("ADO_SIM_DB_PATH")
    if db_path is None:
        raise SettingsError("ADO_SIM_DB_PATH is required: the path of the simulator's SQLite file")
    token_key = get("ADO_SIM_TOKEN_KEY")
    if token_key is None or len(token_key) < MIN_TOKEN_KEY_LENGTH:
        raise SettingsError(
            f"ADO_SIM_TOKEN_KEY is required and must be at least {MIN_TOKEN_KEY_LENGTH} characters"
        )
    port_raw = get("ADO_SIM_PORT") or "8600"
    if not port_raw.isdigit() or not 1 <= int(port_raw) <= 65535:
        raise SettingsError("ADO_SIM_PORT must be an integer between 1 and 65535")
    log_level = (get("ADO_SIM_LOG_LEVEL") or "INFO").upper()
    if log_level not in _LOG_LEVELS:
        raise SettingsError(f"ADO_SIM_LOG_LEVEL must be one of {', '.join(sorted(_LOG_LEVELS))}")
    return Settings(
        db_path=Path(db_path),
        token_key=token_key,
        host=get("ADO_SIM_HOST") or "127.0.0.1",
        port=int(port_raw),
        seed_file=Path(get("ADO_SIM_SEED_FILE") or "seed/demo.yaml"),
        busy_timeout_seconds=parse_duration(
            "ADO_SIM_BUSY_TIMEOUT", get("ADO_SIM_BUSY_TIMEOUT") or "30s"
        ),
        log_level=log_level,
        otlp_endpoint=get("ADO_SIM_OTLP_ENDPOINT"),
    )
