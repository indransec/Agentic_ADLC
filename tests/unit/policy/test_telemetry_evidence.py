"""T004 (012 research R-03, contracts/telemetry-evidence.md): ``telemetry`` from the pilot's
observability and monitors, mapped by the evidence-sources catalogue (no metric names in code)."""

import json
import time
from collections.abc import Mapping
from typing import Any

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Evidence
from adlc.policy.pilot_evidence import PilotEvidence
from adlc.policy.values import NOT_AVAILABLE
from adlc.tools.token import verify

KEY = "k" * 32
CTX = EvalContext("T8", "CTL-T8-01", "UC-0001/T8/run-1", "UC-0001")
MAPPING = {
    "online_eval_score": {"metric": "accuracy"},
    "pii_leak_count": {"metric": "pii_outputs"},
    "availability_pct": {"ratio": ["answered", "sent"], "scale": 100},
    "cost_per_task_usd": {"ratio": ["cost", "requests"]},
}
CATALOGUE = {"evidence_sources": [{"id": "telemetry", "fields": [], "from_pilot": MAPPING}]}


class Pilot:
    def __init__(self, metrics: Mapping[str, Any], monitors: list[dict[str, Any]]) -> None:
        self.metrics, self.monitors = dict(metrics), monitors
        self.tokens: list[Any] = []

    def __call__(
        self, host: str, server: str, tool: str, args: Mapping[str, Any], token: str
    ) -> tuple[bool, str]:
        self.tokens.append(verify(token, KEY, scope=None, now=time.time()))
        if (server, tool) == ("observability", "metrics"):
            return False, json.dumps({"metrics": self.metrics})
        if (server, tool) == ("monitoring", "read"):
            return False, json.dumps({"monitors": self.monitors})
        return True, "not here"


def _evidence(pilot: Pilot, catalogue: Mapping[str, Any] | None = CATALOGUE) -> Any:
    found = PilotEvidence(pilot, KEY)  # type: ignore[arg-type]
    found.catalogue = lambda name: catalogue if name == "evidence_sources" else None
    return found.get("telemetry", CTX)


METRICS = {
    "accuracy": 0.93,
    "pii_outputs": 0,
    "answered": 99,
    "sent": 100,
    "cost": 1.5,
    "requests": 50,
}


def test_fields_come_from_the_mapped_metrics() -> None:
    answer = _evidence(Pilot(METRICS, [{"metric": "accuracy"}, {"metric": "cost"}]))
    assert isinstance(answer, Evidence) and not answer.synthetic
    assert answer.value == {
        "online_eval_score": 0.93,
        "pii_leak_count": 0,
        "availability_pct": 99.0,
        "cost_per_task_usd": 0.03,
        "monitors": {"accuracy": True, "cost": True},
    }


def test_unmeasured_fields_are_absent_and_their_monitors_not_reporting() -> None:
    metrics = {**METRICS, "accuracy": None, "sent": 0}
    answer = _evidence(Pilot(metrics, [{"metric": "accuracy"}]))
    assert isinstance(answer, Evidence)
    assert "online_eval_score" not in answer.value and "availability_pct" not in answer.value
    assert answer.value["monitors"] == {"accuracy": False}


def test_no_monitors_configured_is_an_empty_map() -> None:
    answer = _evidence(Pilot(METRICS, []))
    assert isinstance(answer, Evidence) and answer.value["monitors"] == {}


def test_the_service_token_names_the_use_case_and_reads_only() -> None:
    pilot = Pilot(METRICS, [])
    _evidence(pilot)
    assert {t.usecase_id for t in pilot.tokens} == {"UC-0001"}
    assert all(scope.endswith(":read") for t in pilot.tokens for scope in t.scopes)


def test_without_a_mapping_telemetry_is_not_available() -> None:
    assert _evidence(Pilot(METRICS, []), catalogue=None) is NOT_AVAILABLE
