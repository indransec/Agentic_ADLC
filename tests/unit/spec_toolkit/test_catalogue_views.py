"""T015: typed views over the shared catalogues of the valid fixture bundle."""

from pathlib import Path

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.loader import load_bundle
from tests.support.spec_fixtures import build_bundle


def test_views(tmp_path: Path) -> None:
    cats = Catalogues.from_bundle(load_bundle(build_bundle(tmp_path)))
    assert {"business_owner", "adlc_coe"} <= cats.role_ids
    assert cats.risk_tier_rank == {"low": 1, "medium": 2, "high": 3}
    assert "usecase.submitted" in cats.external_events
    assert "drift" in cats.operational_events
    assert "implementation" in cats.root_causes
    assert cats.change_class_rank["major"] > cats.change_class_rank["minor"]
    assert cats.data_class_rank["internal"] < cats.data_class_rank["confidential"]
    assert "reasoning" in cats.model_tiers
    assert "read" in cats.mcp_scopes["confluence"]
    assert "write" in cats.permission_verbs
    assert "build" in cats.duty_groups
    assert "free_text" in cats.evidence_sources["intake"]
    assert cats.route_destinations["human_completion"] == "human"
    assert cats.predicates["evidence_exists"].params[0].kind == "evidence_ref"
    assert cats.metrics["task_success_rate"].unit == "ratio"
    guard = cats.guardrails["injection_success_max"]
    assert (
        guard.direction == "max"
        and guard.tighten_only
        and guard.values["high"] <= guard.values["low"]
    )
