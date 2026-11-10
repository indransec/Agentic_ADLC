"""Typed settings read from the environment only (contracts/settings.md, FR-013 to FR-015).

``DatabaseSettings`` is what migrations need; ``Settings`` adds what the API and the
``adlc-account`` CLI need. Values are never echoed: secret fields are ``SecretStr``, and the
error formatter in :mod:`adlc.config.errors` prints field names and expected forms only.
"""

import os
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from adlc.config.durations import DURATION_FORM, Duration
from adlc.identity.catalogue import load_role_ids

ENV_PREFIX = "ADLC_"
# Attachments the ledger accepts by default (005 contracts/storage.md); no macro formats.
DEFAULT_ATTACHMENT_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/pdf",
        "image/png",
        "image/svg+xml",
        "text/plain",
        "text/markdown",
    }
)


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


class RuntimeSettings(DatabaseSettings):
    """Settings shared by the long-running processes (API and orchestrator)."""

    db_app_password: SecretStr = Field(
        min_length=16, json_schema_extra=_meta("at least 16 characters", secret=True)
    )
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

    file_store_dir: Path = Field(
        default=Path("data/files"), json_schema_extra=_meta("path to the file store folder")
    )
    attachment_max: int = Field(
        default=25_000_000, gt=0, json_schema_extra=_meta("bytes, or a number with kB or MB")
    )
    attachment_types: Annotated[frozenset[str], NoDecode] = Field(
        default=DEFAULT_ATTACHMENT_TYPES, json_schema_extra=_meta("comma-separated media types")
    )

    @field_validator("role_catalogue")
    @classmethod
    def _readable_catalogue(cls, value: Path) -> Path:
        return _readable(value)

    @field_validator("attachment_max", mode="before")
    @classmethod
    def _bytes(cls, value: object) -> object:
        if isinstance(value, str):
            match = re.fullmatch(r"\s*([0-9]+)\s*(kB|MB)?\s*", value)
            if match is None:
                raise ValueError("expected bytes, or a number with kB or MB")
            return int(match[1]) * {None: 1, "kB": 1_000, "MB": 1_000_000}[match[2]]
        return value

    @field_validator("attachment_types", mode="before")
    @classmethod
    def _media_types(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(part.strip() for part in value.split(",") if part.strip())
        return value


class Settings(RuntimeSettings):
    """Settings for the platform API and the account CLI."""

    session_secret: SecretStr = Field(
        min_length=32, json_schema_extra=_meta("at least 32 characters", secret=True)
    )
    session_ttl: Duration = Field(
        default=timedelta(hours=8), json_schema_extra=_meta(DURATION_FORM)
    )
    accounts_file: Path = Field(json_schema_extra=_meta("path to a readable file"))

    @field_validator("accounts_file")
    @classmethod
    def _readable_accounts(cls, value: Path) -> Path:
        return _readable(value)


LEASE_MARGIN_S = 30.0  # an agent timeout plus this margin must fit inside the lease (006 FR-015)


class AgentLimit(BaseModel):
    """Limits of one agent attempt (006 FR-014)."""

    steps: int = Field(gt=0)
    tokens: int = Field(gt=0)
    timeout_s: float = Field(gt=0)


class AgentLimitOverride(BaseModel):
    """Per-terminal overrides; unset fields keep the tier's limit."""

    steps: int | None = Field(default=None, gt=0)
    tokens: int | None = Field(default=None, gt=0)
    timeout_s: float | None = Field(default=None, gt=0)


DEFAULT_AGENT_LIMITS: dict[str, AgentLimit] = {
    "reasoning": AgentLimit(steps=8, tokens=400_000, timeout_s=240),
    "coding": AgentLimit(steps=8, tokens=400_000, timeout_s=240),
    "standard": AgentLimit(steps=6, tokens=200_000, timeout_s=120),
}


class OrchestratorSettings(RuntimeSettings):
    """Settings for the ``adlc-orchestrator`` process (003 research R-11)."""

    time_scale: float = Field(
        default=1.0, gt=0, json_schema_extra=_meta("number greater than zero")
    )
    poll_interval: Duration = Field(
        default=timedelta(seconds=1), json_schema_extra=_meta(DURATION_FORM)
    )
    lease: Duration = Field(default=timedelta(minutes=5), json_schema_extra=_meta(DURATION_FORM))
    heartbeat_max_age: Duration = Field(
        default=timedelta(seconds=30), json_schema_extra=_meta(DURATION_FORM)
    )
    deadletter_role: str = Field(json_schema_extra=_meta("a role id from the role catalogue"))
    synthetic_dir: Path | None = Field(
        default=Path("data/synthetic"),
        json_schema_extra=_meta("path to the synthetic data folder, or off"),
    )
    accounts_file: Path | None = Field(
        default=None, json_schema_extra=_meta("path to a readable file (optional)")
    )

    # 006 agent runtime
    anthropic_api_key: SecretStr | None = Field(
        default=None, json_schema_extra=_meta("provider API key", secret=True)
    )
    openai_api_key: SecretStr | None = Field(
        default=None, json_schema_extra=_meta("provider API key", secret=True)
    )
    gemini_api_key: SecretStr | None = Field(
        default=None, json_schema_extra=_meta("provider API key", secret=True)
    )
    model_profile: str = Field(
        default="default",
        pattern=r"^[a-z][a-z0-9_]*$",
        json_schema_extra=_meta("a profile name of the model catalogue, e.g. default or dev"),
    )
    reviewer_mode: Literal["stub", "model"] = Field(
        default="stub", json_schema_extra=_meta("stub or model")
    )
    agent_limits: dict[str, AgentLimit] = Field(
        default_factory=lambda: dict(DEFAULT_AGENT_LIMITS),
        json_schema_extra=_meta(
            'JSON per tier: {"<tier>": {"steps", "tokens", "timeout_s"}}; each timeout plus 30 s '
            "shorter than the lease"
        ),
    )
    agent_limit_overrides: dict[str, AgentLimitOverride] = Field(
        default_factory=dict,
        json_schema_extra=_meta(
            'JSON per terminal id: {"<terminal>": {"timeout_s": 200}}; each timeout plus 30 s '
            "shorter than the lease"
        ),
    )
    agent_corrections: int = Field(
        default=2, ge=0, le=10, json_schema_extra=_meta("whole number from 0 to 10")
    )
    model_outage_limit: Duration = Field(
        default=timedelta(minutes=30), json_schema_extra=_meta(DURATION_FORM)
    )
    cost_alert_levels: Annotated[tuple[Decimal, ...], NoDecode] = Field(
        default=(Decimal("5"), Decimal("20"), Decimal("50")),
        json_schema_extra=_meta("comma-separated USD amounts, e.g. 5,20,50"),
    )

    def provider_keys(self) -> dict[str, str | None]:
        """Provider (as the model catalogue names it) to API key; None means no key (006)."""
        keys = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
        }
        return {p: None if k is None else k.get_secret_value() for p, k in keys.items()}

    @field_validator("agent_limits", mode="after")
    @classmethod
    def _merge_tier_defaults(
        cls, value: dict[str, AgentLimit], info: ValidationInfo
    ) -> dict[str, AgentLimit]:
        merged = {**DEFAULT_AGENT_LIMITS, **value}
        _fits_lease(info, [limit.timeout_s for limit in merged.values()])
        return merged

    @field_validator("agent_limit_overrides", mode="after")
    @classmethod
    def _overrides_fit_lease(
        cls, value: dict[str, AgentLimitOverride], info: ValidationInfo
    ) -> dict[str, AgentLimitOverride]:
        _fits_lease(info, [o.timeout_s for o in value.values() if o.timeout_s is not None])
        return value

    @field_validator("cost_alert_levels", mode="before")
    @classmethod
    def _levels(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                levels = tuple(Decimal(p.strip()) for p in value.split(",") if p.strip())
            except InvalidOperation:
                raise ValueError("expected comma-separated USD amounts") from None
            if any(level <= 0 for level in levels):
                raise ValueError("amounts must be greater than zero")
            return tuple(sorted(levels))
        return value

    @field_validator("synthetic_dir", mode="before")
    @classmethod
    def _off_disables(cls, value: object) -> object:
        return None if isinstance(value, str) and value.strip().lower() == "off" else value

    @field_validator("accounts_file")
    @classmethod
    def _readable_optional(cls, value: Path | None) -> Path | None:
        return None if value is None else _readable(value)

    @field_validator("deadletter_role")
    @classmethod
    def _known_role(cls, value: str, info: ValidationInfo) -> str:
        catalogue = info.data.get("role_catalogue")
        if isinstance(catalogue, Path) and value not in load_role_ids(catalogue):
            raise ValueError("not a role in the role catalogue")
        return value


def _fits_lease(info: ValidationInfo, timeouts: list[float]) -> None:
    """006 FR-015: a running agent step must never outlive the worker's lease on it."""
    lease = info.data.get("lease")
    if isinstance(lease, timedelta) and any(
        t + LEASE_MARGIN_S >= lease.total_seconds() for t in timeouts
    ):
        raise ValueError("an agent timeout plus 30 s must be shorter than the lease")


def _readable(value: Path) -> Path:
    path = value.expanduser()
    if not path.is_file() or not os.access(path, os.R_OK):
        raise ValueError("not a readable file")
    return path


def env_name(field_name: str) -> str:
    """Environment variable name for a settings field."""
    return f"{ENV_PREFIX}{field_name.upper()}"
