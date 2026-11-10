"""T014: record, signature, waiver and directory predicates."""

from tests.unit.policy.conftest import Check, fails, passes

T = {
    "T0": {
        "status": "pass",
        "signed_roles": ["business_owner"],
        "risk_classification": [{"tier": "low"}],
    },
    "T4": {"status": "rework", "regression_pack": [{"pack_id": "p"}]},
    "T7": {"status": "pass", "registry_entry": [{"agent_id": "a"}]},
    "T8": {"status": "pass", "monitors": [{"status": "paused"}]},
    "T5": {"status": "open", "assurance_attestation": [{"role": "x"}]},
}
WAIVERS = {
    "waivers": [
        {"waiver_id": "WVR-0001", "run_id": "r", "expiry": "2026-12-01", "status": "approved"}
    ]
}


def test_evidence_exists(check: Check) -> None:
    passes(check("evidence_exists(T0.risk_classification.tier)", T))
    fails(
        check("evidence_exists(T0.risk_classification)", {"T0": {"risk_classification": []}}),
        "T0.risk_classification is empty",
    )
    fails(
        check("evidence_exists(T0.value_hypothesis)", T),
        "evidence not available: T0.value_hypothesis",
    )


def test_signed_frozen_live(check: Check) -> None:
    passes(check("is_signed(T0.risk_classification)", T))
    fails(check("is_signed(T4.regression_pack)", T), "T4 is not signed (status rework)")
    passes(check("is_frozen(T4.regression_pack)", T))
    fails(check("is_frozen(T5.assurance_attestation)", T), "T5 run is still open")
    passes(check("is_live(T7.registry_entry)", T))
    fails(check("is_live(T8.monitors)", T), "T8.monitors row 1: status is 'paused'")
    fails(check("is_live(T4.regression_pack)", T), "T4 is not live")


def test_provisioned_pinned(check: Check) -> None:
    env = {
        "env": {"dev": {"provisioned": True}, "test": {"provisioned": "no"}},
        "template": {"version": "1.4.2", "loose": "latest"},
    }
    passes(check("is_provisioned(env.dev)", env))
    fails(check("is_provisioned(env.test)", env), "env.test is not provisioned")
    passes(check("is_pinned(template.version)", env))
    fails(check("is_pinned(template.loose)", env), "version 'latest' is not pinned")


def test_directory(check: Check) -> None:
    sources = {"directory": ["alice"], "intake": {"business_owner": "alice", "other": "mallory"}}
    passes(check("in_directory(intake.business_owner)", sources))
    fails(check("in_directory(intake.other)", sources), "'mallory' is not in the directory")
    fails(
        check("in_directory(intake.business_owner)", {"intake": {"business_owner": "alice"}}),
        "evidence not available: directory",
    )


def test_approved_by(check: Check) -> None:
    sources = {
        **T,
        "dataset": {"golden": {"approved_by": ["data_owner"]}, "draft": {"approved_by": []}},
    }
    passes(check('approved_by(dataset.golden, "data_owner")', sources))
    fails(
        check('approved_by(dataset.draft, "data_owner")', sources),
        "dataset.draft is not approved by data_owner",
    )
    passes(check('approved_by(T0.risk_classification, "business_owner")', sources))


def test_all_statuses_in(check: Check) -> None:
    passes(check('all_statuses_in(["T0", "T7"], ["pass", "exception"])', T))
    fails(check('all_statuses_in(["T0", "T4"], ["pass", "exception"])', T), "T4 status is rework")
    fails(check('all_statuses_in(["T0", "T3"], ["pass"])', T), "T3 has no closed run")


def test_waivers(check: Check) -> None:
    sources = {**WAIVERS, "release": {"release_date": "2026-11-20", "late": "2027-01-01"}}
    passes(check("no_waiver_expiring_before(release.release_date)", sources))
    fails(
        check("no_waiver_expiring_before(release.late)", sources),
        "waiver WVR-0001 expires 2026-12-01",
    )
    passes(check("no_expired_waivers()", WAIVERS))
    fails(
        check(
            "no_expired_waivers()",
            {"waivers": [{"waiver_id": "WVR-0002", "run_id": "r", "expiry": "2026-01-01"}]},
        ),
        "WVR-0002 expired",
    )
    passes(check('waiver_expiring_within("30d")', WAIVERS))
    fails(check('waiver_expiring_within("14d")', WAIVERS), "no waiver expires within 14d")
