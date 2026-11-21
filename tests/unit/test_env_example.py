"""US3: .env.example documents exactly the settings, with placeholders for secrets (FR-013)."""

from pathlib import Path

from adlc.config.settings import (
    BoardSettings,
    BridgeSettings,
    KnowledgeSettings,
    OrchestratorSettings,
    Settings,
    ToolsSettings,
    UiSettings,
    env_name,
)

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
COMPOSE_ONLY = {
    "ADLC_PHOENIX_UI_PORT",
    "ADLC_UI_PORT",
    "ADO_SIM_TOKEN_KEY",
    "ADO_SIM_PORT",
    "ADO_SIM_DEMO_PASSWORD",  # 017
    "ADO_SIM_PAGE_SESSION_TTL",  # 017
}
# 015: the ADO simulator's own secret, read only by the simulator (not a platform setting)
SIMULATOR_SECRETS = {"ADO_SIM_TOKEN_KEY"}


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
    return names | SIMULATOR_SECRETS


def test_keys_match_settings() -> None:
    fields = (
        set(Settings.model_fields)
        | set(OrchestratorSettings.model_fields)
        | set(UiSettings.model_fields)
        | set(KnowledgeSettings.model_fields)
        | set(ToolsSettings.model_fields)
        | set(BridgeSettings.model_fields)
        | set(BoardSettings.model_fields)
    )
    expected = {env_name(name) for name in fields} | COMPOSE_ONLY
    platform = {k for k in _entries() if not k.startswith(PILOT_PREFIX)}
    assert platform == expected


PILOT_PREFIX = "PILOT_"  # 009: the pilot's own settings, read only by the pilot


def test_pilot_settings_are_separate_and_keyless() -> None:
    """009 A3: pilot settings carry their own prefix, read nothing of the platform's, and the
    model key is empty by default."""
    entries = _entries()
    pilot = {k: v for k, v in entries.items() if k.startswith(PILOT_PREFIX)}
    assert {"PILOT_MODEL_URL", "PILOT_MODEL_NAME", "PILOT_MODEL_API_KEY"} <= set(pilot)
    assert pilot["PILOT_MODEL_API_KEY"] == ""
    assert not any(k.startswith("ADLC_") for k in pilot)


def test_secrets_are_placeholders() -> None:
    entries = _entries()
    for name in _secret_names():
        assert entries[name] == "REPLACE_ME", name


def test_provider_keys_are_empty() -> None:
    """006: a placeholder would count as a configured key; an empty value means no key."""
    entries = _entries()
    for name in ("ADLC_ANTHROPIC_API_KEY", "ADLC_OPENAI_API_KEY", "ADLC_GEMINI_API_KEY"):
        assert entries[name] == "", name


def test_board_token_is_empty() -> None:
    """016: the board is off by default; an empty token means "not issued yet"."""
    entries = _entries()
    assert entries["ADLC_BOARD_TOKEN"] == ""
    assert entries["ADLC_BOARD_ENABLED"] == "false"


def test_the_simulator_demo_password_is_empty() -> None:
    """017: a shared demo password is opt-in; the example never ships one."""
    assert _entries()["ADO_SIM_DEMO_PASSWORD"] == ""
