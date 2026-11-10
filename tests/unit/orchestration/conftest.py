from pathlib import Path
from typing import Any

import pytest

from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"


@pytest.fixture(scope="session")
def registry() -> InMemorySpecRegistry:
    return InMemorySpecRegistry.from_bundle(load_bundle(SPECS))


@pytest.fixture(scope="session")
def pinned(registry: InMemorySpecRegistry) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for n in range(10):
        entry = registry.entry(f"T{n}")
        assert entry is not None
        out[f"T{n}"] = entry.spec
    return out
