"""T014: dev and test environments are created from the package's infrastructure definition
(FR-018 to FR-021, SC-009)."""

from collections.abc import Callable

from tests.integration.conftest import Host, Packages

INCIDENT = {
    "incident_id": "INC-1",
    "title": "Locked out",
    "affected_service": "sso",
    "description": "I am locked out of single sign-on after a password change.",
    "urgency": "high",
}


def test_create_status_triage_delete_and_records(
    host: Callable[[str], Host], packages: Packages
) -> None:
    h = host("dev")
    created = h.client.post("/environment", json={"package_hash": packages.default})
    assert created.status_code == 201, created.text
    assert len(created.json()["replicas"]) == 1
    status = h.client.get("/environment").json()
    assert status["package_hash"] == packages.default
    assert all(r["healthy"] for r in status["replicas"])
    answer = h.client.post("/triage", json=INCIDENT).json()
    assert answer["team"] == "identity-access" and answer["package_hash"] == packages.default
    again = h.client.post("/environment", json={"package_hash": packages.default})
    assert again.status_code == 409
    assert h.client.delete("/environment").status_code == 204
    assert h.client.get("/environment").status_code == 404
    assert h.client.post("/triage", json=INCIDENT).status_code == 404
    recreated = h.client.post("/environment", json={"package_hash": packages.default})
    assert recreated.json()["settings"] == created.json()["settings"]
    operations = [r["operation"] for r in h.record("environments")]
    assert operations == ["create", "create", "delete", "create"]
    assert [r["outcome"] for r in h.record("environments")][1] == "refused"


def test_refusals_create_nothing(host: Callable[[str], Host], packages: Packages) -> None:
    h = host("test")
    unknown = h.client.post("/environment", json={"package_hash": "sha256:" + "0" * 64})
    assert unknown.status_code == 404
    undeclared = h.client.post(
        "/environment", json={"package_hash": packages.default, "settings": {"replicas": "9"}}
    )
    assert undeclared.status_code == 422
    bad_value = h.client.post(
        "/environment",
        json={"package_hash": packages.default, "settings": {"model_mode": "telepathic"}},
    )
    assert bad_value.status_code == 422
    assert h.client.get("/environment").status_code == 404


def test_settings_and_infra_reference(host: Callable[[str], Host], packages: Packages) -> None:
    h = host("test")
    infra = h.client.get("/infra").json()
    assert {d["environment"] for d in infra["definitions"]} == {"dev", "test", "prod-sim"}
    assert all(d["version"] for d in infra["definitions"])
    created = h.client.post(
        "/environment",
        json={"package_hash": packages.default, "settings": {"model_mode": "simulated"}},
    )
    assert created.status_code == 201 and created.json()["settings"] == {"model_mode": "simulated"}


def test_prodsim_has_no_environment_operations(
    host: Callable[[str], Host], packages: Packages
) -> None:
    h = host("prod-sim")
    refused = h.client.post("/environment", json={"package_hash": packages.default})
    assert refused.status_code == 405
