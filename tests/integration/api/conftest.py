"""Fixtures for the 007 API tests: the platform API over the orchestration harness."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.api import Api, api_for
from tests.support.orchestration import Harness


@pytest.fixture
def api(h: Harness, tmp_path: Path) -> Iterator[Api]:
    with api_for(h, tmp_path) as built:
        yield built
