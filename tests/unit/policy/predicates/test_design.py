"""T020: design and build predicates."""

from typing import Any

from tests.unit.policy.conftest import Check, fails, passes

T: dict[str, Any] = {
    "T0": {
        "data_access": [
            {"classification": "confidential", "access_status": "approved"},
            {"classification": "restricted", "access_status": "requested"},
        ]
    },
    "T1": {
        "functional_requirements": [{"req_id": "FR-1"}, {"req_id": "FR-2"}],
        "non_functional_requirements": [
            {"category": "cost", "target": "0.05"},
            {"category": "latency", "target": 2000},
        ],
        "autonomy_levels": [
            {"action": "refund", "hitl_required": "yes"},
            {"action": "lookup", "hitl_required": False},
        ],
    },
    "T2": {
        "design_decisions": [{"req_ids": "FR-1, FR-2"}],
        "partial": [{"req_ids": ["FR-1"]}],
        "tool_api_contracts": [{"mcp_server": "jira"}, {"mcp_server": "new"}],
        "bad_tools": [{"mcp_server": "shadow_api"}],
        "token_budget": [{"max_tokens": 4000, "max_cost_usd": "0.04"}],
        "big_budget": [{"max_tokens": 4000, "max_cost_usd": 0.5}],
        "data_strategy": [{"classification": "confidential"}],
        "risky": [{"classification": "restricted"}],
        "hitl_design": [{"action": "refund"}],
        "security_architecture": [{"control": "claims_db", "layer": "tool"}],
    },
    "T3": {
        "traceability_matrix": [
            {"req_id": "FR-1", "test_id": "t1"},
            {"req_id": "FR-2", "test_id": "t2"},
        ],
        "half": [{"req_id": "FR-1", "test_id": "t1"}, {"req_id": "FR-2", "test_id": ""}],
        "security_build_checks": [
            {"scan": "sast", "critical_count": 0, "high_count": "0"},
            {"scan": "secret_scan", "critical_count": 0, "high_count": 0, "medium_count": 2},
        ],
        "design_conformance": [
            {"decision_id": "D1", "deviation": "none"},
            {"decision_id": "D2", "deviation": "caching added"},
        ],
        "clean": [{"decision_id": "D1", "deviation": ""}],
    },
    "T5": {
        "access_control_matrix": [{"resource": "claims_db"}],
        "wide": [{"resource": "payments_db"}],
    },
}


def test_every_req_mapped(check: Check) -> None:
    passes(check("every_req_mapped(T1.functional_requirements, T2.design_decisions)", T))
    fails(
        check("every_req_mapped(T1.functional_requirements, T2.partial)", T),
        "row 2: FR-2 is not mapped in T2.partial",
    )


def test_every_req_traced(check: Check) -> None:
    passes(
        check('every_req_traced(T1.functional_requirements, T3.traceability_matrix, "test_id")', T)
    )
    fails(
        check('every_req_traced(T1.functional_requirements, T3.half, "test_id")', T),
        "row 2: FR-2 has no test_id in T3.half",
    )


def test_tools(check: Check) -> None:
    passes(check("all_tools_registered_or_flagged(T2.tool_api_contracts)", T))
    fails(
        check("all_tools_registered_or_flagged(T2.bad_tools)", T),
        "T2.bad_tools row 1: 'shadow_api' is not a registered MCP server",
    )


def test_token_budget(check: Check) -> None:
    passes(check("token_budget_within_nfr(T2.token_budget, T1.non_functional_requirements)", T))
    fails(
        check("token_budget_within_nfr(T2.big_budget, T1.non_functional_requirements)", T),
        "max_cost_usd 0.5 is above the cost NFR 0.05",
    )


def test_data_classes(check: Check) -> None:
    passes(check("data_classes_within(T2.data_strategy, T0.data_access)", T))
    fails(
        check("data_classes_within(T2.risky, T0.data_access)", T),
        "T2.risky row 1: restricted is above the approved classification",
    )


def test_hitl(check: Check) -> None:
    passes(check("hitl_covered(T1.autonomy_levels, T2.hitl_design)", T))
    fails(
        check("hitl_covered(T1.autonomy_levels, T2.partial)", T),
        "row 1: 'refund' has no HITL design row",
    )


def test_scan_clean(check: Check) -> None:
    passes(check('scan_clean(T3.security_build_checks, "sast", ["critical", "high"])', T))
    fails(
        check(
            'scan_clean(T3.security_build_checks, "secret_scan", ["critical", "high", "medium"])', T
        ),
        "secret_scan has 2 medium findings",
    )
    fails(check('scan_clean(T3.security_build_checks, "dast", ["critical"])', T), "no dast scan")


def test_permissions_subset(check: Check) -> None:
    passes(check("permissions_subset(T5.access_control_matrix, T2.security_architecture)", T))
    fails(
        check("permissions_subset(T5.wide, T2.security_architecture)", T),
        "'payments_db' is not in the designed controls",
    )


def test_design_deviation(check: Check) -> None:
    passes(check("any_design_deviation(T3.design_conformance)", T))
    fails(check("any_design_deviation(T3.clean)", T), "no design deviation")
