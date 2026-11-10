import os
from pathlib import Path

import pytest

_INTEGRATION_DIR = Path(__file__).parent / "integration"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if _INTEGRATION_DIR in Path(item.path).parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see ADLC_* values exported from a developer's .env (e.g. by make)."""
    for key in list(os.environ):
        if key.startswith("ADLC_"):
            monkeypatch.delenv(key)
    # Tests never export traces; tests/unit/test_tracing.py re-enables the SDK explicitly.
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")


@pytest.fixture(autouse=True)
def _no_model_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """006 (R-13): tests never reach a model provider. Only ``litellm_contract`` tests load
    LiteLLM, and they intercept its HTTP with respx."""
    if request.node.get_closest_marker("litellm_contract") is not None:
        return
    import adlc.agents.gateway as gateway

    def blocked() -> object:
        raise RuntimeError(
            "LiteLLM is blocked in tests; use FakeGateway or a litellm_contract test"
        )

    monkeypatch.setattr(gateway, "_litellm", blocked)
