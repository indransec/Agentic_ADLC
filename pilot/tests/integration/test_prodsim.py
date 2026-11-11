"""T018: prod-sim deployments and the shadow, canary and full split (US4; FR-011, SC-003)."""

import time
from collections.abc import Callable

from tests.integration.conftest import Host, Packages

INCIDENT = {
    "title": "Wi-Fi drops",
    "affected_service": "wifi",
    "urgency": "medium",
    "description": "Office Wi-Fi connection drops every few minutes.",
}


def deploy(h: Host, packages: Packages) -> None:
    for role, package in (("stable", packages.default), ("candidate", packages.variant)):
        answer = h.client.post("/deployments", json={"package_hash": package, "role": role})
        assert answer.status_code == 201, answer.text


def ask(h: Host, n: int) -> list[str]:
    return [
        h.client.post("/triage", json={**INCIDENT, "incident_id": f"INC-T-{i}"}).json()[
            "package_hash"
        ]
        for i in range(n)
    ]


def test_canary_full_and_records(host: Callable[[str], Host], packages: Packages) -> None:
    h = host("prod-sim")
    deploy(h, packages)
    assert set(ask(h, 20)) == {packages.default}  # full by default
    split = h.client.put("/split", json={"mode": "canary", "share": 0.2})
    assert split.status_code == 200 and split.json()["candidate"] == packages.variant
    served = ask(h, 500)
    share = served.count(packages.variant) / len(served)
    assert 0.15 <= share <= 0.25
    assert h.client.put("/split", json={"mode": "full"}).json()["mode"] == "full"
    modes = [r.get("mode") for r in h.record("splits") if r.get("operation") == "split"]
    assert modes == ["canary", "full"]


def test_shadow_never_returns_the_candidate(
    host: Callable[[str], Host], packages: Packages
) -> None:
    h = host("prod-sim")
    deploy(h, packages)
    h.client.put("/split", json={"mode": "shadow"})
    assert set(ask(h, 20)) == {packages.default}
    deadline = time.monotonic() + 10
    while len(h.record("shadow")) < 20 and time.monotonic() < deadline:
        time.sleep(0.05)
    shadow = h.record("shadow")
    assert len(shadow) == 20 and {r["candidate_hash"] for r in shadow} == {packages.variant}


def test_refusals_keep_the_split(host: Callable[[str], Host], packages: Packages) -> None:
    h = host("prod-sim")
    no_candidate = h.client.put("/split", json={"mode": "canary", "share": 0.2})
    assert no_candidate.status_code == 404
    unknown = h.client.post(
        "/deployments", json={"package_hash": "sha256:" + "1" * 64, "role": "candidate"}
    )
    assert unknown.status_code == 404
    assert h.client.get("/split").json()["mode"] == "full"
    assert h.client.post("/triage", json={**INCIDENT, "incident_id": "x"}).status_code == 404


def test_a_failing_candidate_falls_back_to_stable(
    host: Callable[[str], Host], packages: Packages
) -> None:
    h = host("prod-sim")
    deploy(h, packages)
    h.client.put("/split", json={"mode": "canary", "share": 1.0})
    for worker in h.client.app.state.pilot["candidate"].workers:  # type: ignore[attr-defined]
        worker.stop()
    served = ask(h, 10)
    assert set(served) == {packages.default}
    assert h.client.get("/metrics").json()["counts"]["candidate_failures"] == 10
