"""Fixtures for the 006 runtime integration tests."""

from collections.abc import Mapping
from typing import Any

import pytest

from tests.support.orchestration import Harness
from tests.support.pg import PlatformDatabase

from .support import _run


@pytest.fixture
def model_harness(orch_template: PlatformDatabase) -> Any:
    opened: list[Any] = []

    def make(script: Mapping[str, Any], **kwargs: Any) -> tuple[Harness, Any]:
        ctx, h, late = _run(orch_template, script, **kwargs)
        opened.append(ctx)
        return h, late

    yield make
    for ctx in opened:
        ctx.__exit__(None, None, None)
