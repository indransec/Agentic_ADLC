"""Typed settings read from the environment only (contracts/settings.md, FR-013 to FR-015).

``DatabaseSettings`` is what migrations need; ``Settings`` adds what the API and the
``adlc-account`` CLI need. Values are never echoed: secret fields are ``SecretStr``, and the
error formatter in :mod:`adlc.config.errors` prints field names and expected forms only.
"""

import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from adlc.config.durations import DURATION_FORM, Duration

ENV_PREFIX = "ADLC_"


def _meta(form: str, *, secret: bool = False) -> dict[str, Any]:
    return {"form": form, "secret": secret}


class DatabaseSettings(BaseSettings):
    """Settings for the data store identities (migrations, migration-check, API)."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
    )

    env: Literal["dev", "demo"] = Field(json_schema_extra=_meta("dev or demo"))
    db_host: str = Field(min_length=1, json_schema_extra=_meta("hostname"))
    db_port: int = Field(default=5432, ge=1, le=65535, json_schema_extra=_meta("integer 1-65535"))
    db_name: str = Field(
        default="adlc", pattern=r"^[a-z_][a-z0-9_]*$", json_schema_extra=_meta("identifier")
    )
    db_app_user: str = Field(
        default="adlc_app", pattern=r"^[a-z_][a-z0-9_]*$", json_schema_extra=_meta("identifier")
    )
    db_owner_user: str = Field(
        default="adlc_owner", pattern=r"^[a-z_][a-z0-9_]*$", json_schema_extra=_meta("identifier")
    )
    db_owner_password: SecretStr | None = Field(
        default=None, min_length=16, json_schema_extra=_meta("at least 16 characters", secret=True)
    )
    db_connect_timeout: Duration = Field(
        default=timedelta(seconds=60), json_schema_extra=_meta(DURATION_FORM)
    )


class Settings(DatabaseSettings):
    """Settings for the platform API and the account CLI."""

    db_app_password: SecretStr = Field(
        min_length=16, json_schema_extra=_meta("at least 16 characters", secret=True)
    )
    session_secret: SecretStr = Field(
        min_length=32, json_schema_extra=_meta("at least 32 characters", secret=True)
    )
    session_ttl: Duration = Field(
        default=timedelta(hours=8), json_schema_extra=_meta(DURATION_FORM)
    )
    accounts_file: Path = Field(json_schema_extra=_meta("path to a readable file"))
    role_catalogue: Path = Field(
        default=Path("adlc-specs/shared/roles.yaml"),
        json_schema_extra=_meta("path to a readable file"),
        validate_default=True,
    )
    otlp_endpoint: str = Field(
        default="http://jaeger:4318", pattern=r"^https?://", json_schema_extra=_meta("http(s) URL")
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", json_schema_extra=_meta("DEBUG, INFO, WARNING or ERROR")
    )

    @field_validator("accounts_file", "role_catalogue")
    @classmethod
    def _readable_file(cls, value: Path) -> Path:
        path = value.expanduser()
        if not path.is_file() or not os.access(path, os.R_OK):
            raise ValueError("not a readable file")
        return path


def env_name(field_name: str) -> str:
    """Environment variable name for a settings field."""
    return f"{ENV_PREFIX}{field_name.upper()}"
