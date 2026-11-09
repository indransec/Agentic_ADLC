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
