"""T045: authorization order, reasons and properties (contracts/authorization.md)."""

from hypothesis import given
from hypothesis import strategies as st

from adlc.policy.authorization import decide

SPEC = {
    "terminal": {
        "authorities": {
            "allow": [
                "read:ledger.T0",
                "read:knowledge_base",
                "write:T1.artifacts",
                "read:ledger.all",
            ],
            "deny": ["write:ledger.T0", "write:any_other_terminal"],
            "tool_scopes": ["mcp:confluence:read", "mcp:jira:*"],
        }
    }
}
RUN = "UC-0001/T1/run-1"
AGENT = f"agent:{RUN}"


def test_order_and_reasons() -> None:
    assert decide(AGENT, "write", "T1.artifacts", RUN, SPEC) == (
        True,
        "allowed by write:T1.artifacts",
    )
    assert decide(AGENT, "write", "ledger.T0", RUN, SPEC) == (False, "denied by write:ledger.T0")
    assert decide(AGENT, "deploy", "prod", RUN, SPEC) == (
        False,
        "no allow entry matches deploy:prod",
    )
    assert decide(AGENT, "read", "ledger.T5", RUN, SPEC)[0]  # read:ledger.all means read:ledger.*
    assert decide(AGENT, "mcp", "jira:read", RUN, SPEC) == (
        True,
        "allowed by tool scope mcp:jira:*",
    )
    assert decide(AGENT, "mcp", "github:write", RUN, SPEC) == (
        False,
        "tool not in scope: mcp:github:write",
    )
    other = "UC-0001/T1/run-2"
    assert decide(AGENT, "write", "T1.artifacts", other, SPEC) == (
        False,
        f"out of scope: {AGENT} is bound to {RUN}",
    )
    assert decide("agent", "write", "T1.artifacts", RUN, SPEC) == (
        False,
        "out of scope: agent is bound to no run",
    )
    assert decide(AGENT, "write", "T1.artifacts", None, SPEC)[0] is False
    assert decide(AGENT, "write", "T1.artifacts", RUN, None) == (
        False,
        "no allow entry matches write:T1.artifacts",
    )


def test_deny_applies_to_tools_too() -> None:
    spec = {"terminal": {"authorities": {"tool_scopes": ["mcp:*"], "deny": ["mcp:prod_db:*"]}}}
    assert decide(AGENT, "mcp", "prod_db:write", RUN, spec) == (False, "denied by mcp:prod_db:*")


words = st.text(alphabet="abcdefT0123456789._", min_size=1, max_size=12)


@given(words, words)
def test_deny_always_wins(verb: str, resource: str) -> None:
    spec = {"terminal": {"authorities": {"allow": ["*"], "deny": [f"{verb}:{resource}"]}}}
    assert decide(AGENT, verb, resource, RUN, spec)[0] is False


@given(words, words)
def test_no_allow_match_is_refused(verb: str, resource: str) -> None:
    spec = {"terminal": {"authorities": {"allow": ["never:matches"]}}}
    assert decide(AGENT, verb, resource, RUN, spec)[0] is False


@given(words)
def test_other_run_is_refused(suffix: str) -> None:
    spec = {"terminal": {"authorities": {"allow": ["*"]}}}
    assert decide(f"agent:UC-0001/T1/run-{suffix}x", "write", "T1.artifacts", RUN, spec)[0] is False


def test_mode_scopes_are_granted_only_in_their_mode() -> None:
    """012 (FR-009, US5): a scope granted only in retire mode is refused in any other."""
    from adlc.policy.authorization import decide

    spec = {
        "terminal": {
            "authorities": {
                "tool_scopes": ["mcp:iam:read"],
                "tool_scopes_by_mode": {"retire": ["mcp:iam:revoke"]},
            }
        }
    }
    actor, run = "agent:UC-1/T9/run-1", "UC-1/T9/run-1"
    assert decide(actor, "mcp:iam", "revoke", run, spec, "retire")[0]
    allowed, reason = decide(actor, "mcp:iam", "revoke", run, spec, "evolve")
    assert not allowed and "granted only in mode retire" in reason
    assert not decide(actor, "mcp:iam", "revoke", run, spec)[0]
    assert decide(actor, "mcp:iam", "read", run, spec, "evolve")[0]
