from collections.abc import Iterator

import pytest

from tests.support.orchestration import Harness, build_template, harness
from tests.support.pg import PlatformDatabase


@pytest.fixture(scope="session")
def orch_template(platform_db: PlatformDatabase) -> PlatformDatabase:
    build_template(platform_db)
    return platform_db


@pytest.fixture
def h(orch_template: PlatformDatabase) -> Iterator[Harness]:
    with harness(orch_template) as built:
        yield built
