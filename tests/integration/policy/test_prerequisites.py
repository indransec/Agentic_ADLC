"""T015: prerequisites with the real engine (US1)."""

import shutil
from pathlib import Path

from ruamel.yaml import YAML

from adlc.orchestration.stubs import StubAgent
from tests.support.lifecycle import walk_to
from tests.support.orchestration import SYNTHETIC, Harness, harness, person
from tests.support.pg import PlatformDatabase


def test_t1_prerequisites_pass_after_t0(h: Harness) -> None:
    usecase, t1 = walk_to(h, "T1")
    assert h.run(t1).state == "awaiting_sign_off"
    checks = h.sql(
        "SELECT check_id, passed FROM run.policy_decision WHERE run_id = :r AND check_id LIKE 'PRE-%' ORDER BY policy_decision_id",
        r=t1,
    )
    assert [tuple(c) for c in checks] == [
        ("PRE-T1-01", True),
        ("PRE-T1-02", True),
        ("PRE-T1-03", True),
    ]


def test_missing_evidence_blocks_with_its_path(orch_template: PlatformDatabase) -> None:
    omit = {"value_hypothesis": None}
    agent = StubAgent({"T0": {n: omit for n in range(1, 5)}})
    with harness(orch_template, agent=agent) as h:
        usecase = h.submit()
        t0 = h.active(usecase, "T0")
        assert (t0.state, t0.escalation_trigger) == ("escalated", "retry_limit")  # CTL-T0-01
        # The owner completes T0 by hand, still without a value hypothesis, and passes it.
        h.service.complete_escalation(person("business_owner"), t0.run_id, {})
        h.pass_run(t0.run_id, {"risk_tier": "medium"})
        t1 = h.active(usecase, "T1")
        assert t1.state == "blocked"
        reason = h.sql(
            "SELECT reason FROM run.policy_decision WHERE run_id = :r AND check_id = 'PRE-T1-03'",
            r=t1.run_id,
        )[0][0]
        assert reason == "evidence not available: T0.value_hypothesis"


def test_warn_prerequisite_is_recorded_and_the_run_proceeds(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    synthetic = tmp_path / "synthetic"
    shutil.copytree(SYNTHETIC, synthetic)
    evidence = YAML(typ="safe").load((synthetic / "evidence.yaml").read_text())
    del evidence["change"]["window_requested"]
    yaml = YAML()
    with (synthetic / "evidence.yaml").open("w") as out:
        yaml.dump(evidence, out)
    with harness(orch_template, synthetic_dir=synthetic) as h:
        usecase, t6 = walk_to(h, "T6")
        assert h.run(t6).state == "awaiting_sign_off"  # warn does not block (US1/AC3)
        row = h.sql(
            "SELECT passed, reason FROM run.policy_decision WHERE run_id = :r AND check_id = 'PRE-T6-03'",
            r=t6,
        )[0]
        assert tuple(row) == (False, "evidence not available: change.window_requested")
