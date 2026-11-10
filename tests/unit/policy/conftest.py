from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from adlc.orchestration.interfaces import EvalContext, EvalResult
from adlc.policy.engine import CelPolicyEngine
from adlc.policy.evidence import InMemoryEvidenceProvider
from adlc.policy.predicates import load_all
from adlc.policy.store import MemorySink
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture(scope="session")
def registry() -> InMemorySpecRegistry:
    return InMemorySpecRegistry.from_bundle(load_bundle(SPECS))


Check = Callable[..., EvalResult]


@pytest.fixture
def check(registry: InMemorySpecRegistry) -> Check:
    """Evaluate ``expression`` over in-memory ``sources``; ``spec`` is the run's terminal spec."""

    def run(
        expression: str,
        sources: Mapping[str, Any],
        *,
        terminal: str = "T1",
        spec: Mapping[str, Any] | None = None,
        check_id: str = "CTL-TEST",
    ) -> EvalResult:
        catalogue = registry.catalogue("predicates")
        assert catalogue is not None
        engine = CelPolicyEngine(
            InMemoryEvidenceProvider(sources),
            load_all(),
            catalogue=lambda name: c.content if (c := registry.catalogue(name)) else None,
            spec_for=lambda ctx: spec,
            sink=MemorySink(),
            clock=FixedClock(),
            predicate_catalogue=catalogue.content,
        )
        return engine.evaluate(
            expression, EvalContext(terminal, check_id, f"UC-0001/{terminal}/run-1", "UC-0001")
        )

    return run


def passes(result: EvalResult) -> None:
    assert result.passed, result.reason


def fails(result: EvalResult, *fragments: str) -> None:
    assert not result.passed
    for fragment in fragments:
        assert fragment in result.reason, result.reason
