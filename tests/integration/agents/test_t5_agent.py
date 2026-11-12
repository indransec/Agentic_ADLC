"""011 T019 (US3; FR-009, FR-010, FR-003; SC-003): the T5 assurance agent runs the red-team suite
and the personal-data scan on the candidate; T5's controls read those results; the kill-switch gap
it cannot test ends as an exception only after a person accepts the waiver; the attestation is the
people's sign-off, never the agent's."""

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import text

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import SqlEvidenceProvider
from adlc.policy.synthetic import load_synthetic_artifacts
from adlc.spec_toolkit.registry import SqlSpecRegistry
from tests.support.acting import acting, tool
from tests.support.fake_pilot import FakePilot
from tests.support.orchestration import SYNTHETIC, Harness, person
from tests.support.pg import PlatformDatabase

SYN = load_synthetic_artifacts(SYNTHETIC)
AGENT = "t5-assurance-agent"
CANDIDATE = "sha256:" + "5a" * 32
WAIVER = {
    "risk_acceptance": "accepted",
    "expiry": "2099-12-31",
    "compensating_control": "kill switch checked at release (T7)",
}


def outputs(messages: Sequence[Mapping[str, str]], name: str) -> dict[str, Any]:
    marker = f'<data source="tool:{name}">'
    for message in reversed(messages):
        content = message["content"]
        if message["role"] == "user" and marker in content:
            found: dict[str, Any] = json.loads(
                content[content.index(marker) + len(marker) : content.rindex("</data>")]
            )
            return found
    return {}


class Assurance:
    def __init__(self) -> None:
        self.redteam: dict[str, Any] = {}
        self.scan: dict[str, Any] = {}

    def answer(self, messages: Sequence[Mapping[str, str]]) -> str:
        self.redteam = outputs(messages, "redteam_harness_run") or self.redteam
        self.scan = outputs(messages, "dlp_scanner_run") or self.scan
        rows = copy.deepcopy(SYN["T5"])
        rows.pop("assurance_attestation")  # people sign it
        rows["threat_model_results"] = [
            {
                "threat_id": f"TH-{c}",
                "threat": c,
                "test": f"{self.redteam['suite']} {self.redteam['suite_version']}",
                "result": "mitigated" if v["rate"] == 0 else "open",
                "residual_risk": "low",
            }
            for c, v in self.redteam["by_category"].items()
        ]
        rows["security_control_evidence"] = [
            {
                "control_id": "SEC-01",
                "implemented": True,
                "evidence_link": self.redteam["result_id"],
            }
        ]
        rows["resilience_verification"] = [
            {
                "scenario": "safe_fail",
                "expected_fallback": "first line with review",
                "observed": "first line with review",
                "result": "pass",
            },
            {
                "scenario": "kill_switch",
                "expected_fallback": "stop",
                "observed": "not run in test",
                "result": "fail",
            },
        ]
        rows["residual_risk_register"].append(
            {
                "risk_id": "R-KS",
                "risk": "kill switch untested before release",
                "rating": "medium",
                "risk_owner": "risk_owner",
                "decision": "exception",
                "review_date": "2027-03-31",
            }
        )
        return json.dumps({"artifacts": rows})


def script(assurance: Assurance, retries: int) -> list[Any]:
    first = [
        tool("pilot_env_create"),
        tool("redteam_harness_run"),
        tool("dlp_scanner_run", {"dataset_id": "pii"}),
        tool("control_library_read", {"topic": "security"}),
        tool("iam_read"),
        tool(
            "grc_write",
            {
                "title": "Assurance",
                "report": "Red team clean; personal-data scan clean; kill switch untested in test.",
            },
        ),
        assurance.answer,
    ]
    return first + [assurance.answer] * retries


def to_t5(h: Harness) -> tuple[str, Any]:
    usecase = h.submit()
    h.pass_run(h.active(usecase, "T0").run_id, {"risk_tier": "low"})
    for terminal in ("T1", "T2", "T3", "T4"):
        h.pass_run(h.active(usecase, terminal).run_id)
    return usecase, h.active(usecase, "T5")


def test_t5_assures_from_results_and_the_gap_needs_a_waiver(
    orch_template: PlatformDatabase, tmp_path: Path
) -> None:
    fake = FakePilot()
    fake.packages[CANDIDATE] = {"package_hash": CANDIDATE, "template_id": "fake", "files": {}}
    # T4 (a stub here) leaves the candidate running in test, as the real T4 agent does
    fake.hosts["test"].running = {
        "environment": "test",
        "package_hash": CANDIDATE,
        "replicas": [{"id": "test-1", "healthy": True}],
        "settings": {},
    }
    assurance = Assurance()
    with acting(
        orch_template, {AGENT: script(assurance, retries=3)}, (AGENT,), tmp_path, fake
    ) as a:
        usecase, run = to_t5(a.h)
        a.h.drain()
        run = a.h.run(run.run_id)
        assert run.state == "escalated"
        failed = {c["id"] for c in run.control_results if not c["passed"]}
        assert failed == {"CTL-T5-05"}, failed  # only the kill-switch scenario
        with a.h.app.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT check_id, passed, synthetic FROM run.policy_decision WHERE run_id = :r AND check_id IN ('CTL-T5-01', 'CTL-T5-02', 'CTL-T5-03')"
                ),
                {"r": run.run_id},
            ).all()
            reports = conn.execute(
                text("SELECT count(*) FROM tools.enterprise_record WHERE system = 'grc'")
            ).scalar_one()
        assert rows and all(p and not s for _, p, s in rows)  # red team and scan: real results
        assert reports == 1
        assert "assurance_attestation" not in run.artifacts
        a.h.service.complete_escalation(person("security_officer"), run.run_id, run.artifacts)
        a.h.drain()
        a.h.service.decide(
            person("security_officer"),
            run.run_id,
            "exception",
            reason="kill switch tested at release",
            fields=WAIVER,
        )
        a.h.drain()
        assert (
            a.h.run(run.run_id).state == "awaiting_sign_off"
        )  # a waiver is pending; nothing closes yet
        a.h.service.decide_waiver(person("risk_owner"), "WVR-0001", True, "accepted until release")
        a.h.drain()
        assert a.h.run(run.run_id).final_status == "exception"
        assert a.h.active(usecase, "T6").trigger_event_type == "T5.exception"
        record = SqlEvidenceProvider(a.h.app, SqlSpecRegistry(a.h.app), a.h.clock).get(
            "T5", EvalContext("T6", "x", a.h.active(usecase, "T6").run_id, usecase)
        )
        attestation = record.value["assurance_attestation"]  # type: ignore[union-attr]
        assert (
            attestation
            and attestation[0]["role"] == "security_officer"
            and attestation[0]["decision"] == "exception"
        )
