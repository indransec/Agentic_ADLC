"""US3: .env.example documents exactly the settings, with placeholders for secrets (FR-013)."""

from pathlib import Path

from adlc.config.settings import (
    KnowledgeSettings,
    OrchestratorSettings,
    Settings,
    UiSettings,
    env_name,
)

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
COMPOSE_ONLY = {"POSTGRES_PASSWORD", "ADLC_API_PORT", "ADLC_JAEGER_UI_PORT", "ADLC_UI_PORT"}


def _entries() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            entries[key] = value
    return entries


def _secret_names() -> set[str]:
    names = set()
    for name, field in Settings.model_fields.items():
        extra = field.json_schema_extra
        if isinstance(extra, dict) and extra.get("secret"):
            names.add(env_name(name))
    return names | {"POSTGRES_PASSWORD"}


def test_keys_match_settings() -> None:
    fields = (
        set(Settings.model_fields)
        | set(OrchestratorSettings.model_fields)
        | set(UiSettings.model_fields)
        | set(KnowledgeSettings.model_fields)
    )
    expected = {env_name(name) for name in fields} | COMPOSE_ONLY
    assert set(_entries()) == expected


def test_secrets_are_placeholders() -> None:
    entries = _entries()
    for name in _secret_names():
        assert entries[name] == "REPLACE_ME", name


def test_provider_keys_are_empty() -> None:
    """006: a placeholder would count as a configured key; an empty value means no key."""
    entries = _entries()
    for name in ("ADLC_ANTHROPIC_API_KEY", "ADLC_OPENAI_API_KEY", "ADLC_GEMINI_API_KEY"):
        assert entries[name] == "", name
