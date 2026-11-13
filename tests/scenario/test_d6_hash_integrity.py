"""014 T012 (D-6): what T4 tested is what T7 deployed: one package hash from T3 to production."""

from pathlib import Path

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Evidence, SqlEvidenceProvider
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.scenario.demo_run import demo_run
from tests.support.pg import PlatformDatabase


def test_d6_one_hash_from_build_to_production(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    with demo_run(orch_template, tmp_path) as d:
        provider = SqlEvidenceProvider(d.h.app, SqlSpecRegistry(d.h.app), d.h.clock)
        t9 = d.h.runs(d.main)[-1].run_id
        ctx = EvalContext("T9", "x", t9, d.main)

        def record(terminal: str) -> dict:  # type: ignore[type-arg]
            answer = provider.get(terminal, ctx)
            assert isinstance(answer, Evidence)
            return dict(answer.value)

        candidate = record("T3")["candidate_package"][0]["sha256"]
        assert record("T4")["bound_to"] == candidate
        assert record("T5")["bound_to"] == candidate
        assert record("T6")["deployment_package"][0]["sha256"] == candidate
        deployed = d.io.pilot.hosts["prod-sim"].stable
        assert deployed == candidate
        rerun = [r for r in d.h.runs(d.main) if r.terminal_id == "T3"]
        assert len(rerun) == 2  # the rebuilt candidate (after the T4 defect) is the one released
