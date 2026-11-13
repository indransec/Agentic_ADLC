"""T009 (012 FR-012, research R-05): who decides a change comes from the MCP registry."""

from adlc.inbox.changes import approver_role

REGISTRY = {
    "mcp_servers": [
        {"id": "sharepoint", "owner_role": "adlc_coe", "scopes": ["read"]},
        {"id": "servicenow", "owner_role": "release_manager", "scopes": ["change_create"]},
    ]
}


def test_the_itsm_server_owner_decides_changes() -> None:
    assert approver_role(REGISTRY) == "release_manager"


def test_no_itsm_server_means_nobody_decides() -> None:
    assert approver_role({"mcp_servers": []}) is None
    assert approver_role(None) is None
