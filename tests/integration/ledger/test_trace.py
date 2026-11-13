"""014 T019 (US4; FR-008; SC-004): every decision of a use case is traceable to its spec version,
actor and evidence hash; missing links are reported; the chain verification is included."""

from adlc.ledger.trace import KINDS, TraceItem, gaps, trace
from tests.integration.dashboard.walk import walked
from tests.support.pg import PlatformDatabase


def test_a_walked_use_case_is_fully_traceable(orch_template: PlatformDatabase) -> None:
    with walked(orch_template) as w:
        with w.h.app.connect() as conn:
            report = trace(conn, w.usecase)
        counts = report["counts"]
        assert set(counts) == set(KINDS) and all(counts[k] > 0 for k in KINDS), counts
        assert report["gaps"] == [], report["gaps"][:5]
        assert report["traceable"] == 1.0


def test_missing_links_are_gaps() -> None:
    items = [
        TraceItem(
            "sign_off", "UC-1/T1/run-1#3", "1.0.0", "product_owner-person", "sha256:" + "a" * 64
        ),
        TraceItem("control", "UC-1/T1/run-1#CTL-T1-01", None, "policy", "sha256:" + "b" * 64),
        TraceItem("event", "e-1", "1.0.0", "", "sha256:" + "c" * 64),
        TraceItem("artifact", "UC-1/T1/run-1#reqs@1", "1.0.0", "agent", None),
    ]
    found = gaps(items)
    assert [(g["kind"], g["missing"]) for g in found] == [
        ("control", ["spec_version"]),
        ("event", ["actor"]),
        ("artifact", ["hash"]),
    ]
