"""US4: role ids come only from the role catalogue file (FR-019)."""

from pathlib import Path

import pytest

from adlc.identity.catalogue import CatalogueError, load_role_ids

CATALOGUE = Path(__file__).resolve().parents[2] / "adlc-specs" / "shared" / "roles.yaml"
TDS_ROLES = {
    "business_owner",
    "product_owner",
    "solution_architect",
    "engineering_lead",
    "qa_eval_lead",
    "security_officer",
    "privacy_officer",
    "rai_officer",
    "compliance_officer",
    "risk_owner",
    "release_manager",
    "service_owner",
    "sre",
    "data_owner",
    "adlc_coe",
}


def test_repository_catalogue_has_tds_roles() -> None:
    assert load_role_ids(CATALOGUE) == TDS_ROLES


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("roles:\n  - {id: a_b, description: x}\n  - {id: a_b, description: y}\n", "a_b"),
        ("roles:\n  - {id: BadRole, description: x}\n", "BadRole"),
        ("roles:\n  - {id: ok_role, description: ''}\n", "ok_role"),
        ("roles: []\n", "no roles"),
        ("nothing: here\n", "roles"),
    ],
)
def test_invalid_catalogue(tmp_path: Path, body: str, fragment: str) -> None:
    path = tmp_path / "roles.yaml"
    path.write_text(body)
    with pytest.raises(CatalogueError, match=fragment):
        load_role_ids(path)
