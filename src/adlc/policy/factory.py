"""Wire the policy engine for a process (orchestrator, tests): evidence, parameters, decision log.

Kept out of ``adlc.policy.__init__`` so the predicate modules can import the package freely.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from adlc.ledger.profile import SqlProfileSource
from adlc.orchestration import store as run_store
from adlc.orchestration.interfaces import Clock, EvalContext
from adlc.policy.directory import Directory
from adlc.policy.engine import CelPolicyEngine
from adlc.policy.evidence import CompositeEvidenceProvider, SqlEvidenceProvider
from adlc.policy.parameters import ParameterService, ProfileSource
from adlc.policy.predicates import load_all
from adlc.policy.store import DecisionSink, SqlDecisionSink
from adlc.policy.synthetic import SyntheticEvidenceProvider
from adlc.spec_toolkit.registry import SpecRegistry


def build_policy_engine(
    engine: Engine,
    registry: SpecRegistry,
    clock: Clock,
    *,
    synthetic_dir: Path | None = None,
    directory: Directory | None = None,
    profile: ProfileSource | None = None,
    sink: DecisionSink | None = None,
) -> CelPolicyEngine:
    guardrails = _catalogue(registry, "guardrails") or {}
    profile = profile or SqlProfileSource(engine)  # 005: the versioned use-case profile
    real = SqlEvidenceProvider(
        engine,
        registry,
        clock,
        directory=directory,
        parameters=ParameterService(engine, guardrails, profile),
        profile=profile,
    )
    synthetic = SyntheticEvidenceProvider.from_dir(synthetic_dir) if synthetic_dir else None
    return CelPolicyEngine(
        CompositeEvidenceProvider(real, synthetic),
        load_all(),
        catalogue=lambda name: _catalogue(registry, name),
        spec_for=_SpecLookup(engine, registry),
        sink=sink or SqlDecisionSink(engine),
        clock=clock,
        predicate_catalogue=_catalogue(registry, "predicates") or {},
    )


def _catalogue(registry: SpecRegistry, name: str) -> Mapping[str, Any] | None:
    entry = registry.catalogue(name)
    return None if entry is None else entry.content


class _SpecLookup:
    """The pinned spec of the run being checked (cached per run)."""

    def __init__(self, engine: Engine, registry: SpecRegistry) -> None:
        self.engine = engine
        self.registry = registry
        self._cache: dict[str, Mapping[str, Any] | None] = {}

    def __call__(self, context: EvalContext) -> Mapping[str, Any] | None:
        if context.run_id is None:
            return None
        if context.run_id not in self._cache:
            with self.engine.connect() as conn:
                run = run_store.load_run(conn, context.run_id)
            entry = None if run is None else self.registry.entry(run.terminal_id, run.spec_version)
            self._cache[context.run_id] = None if entry is None else entry.spec
        return self._cache[context.run_id]
