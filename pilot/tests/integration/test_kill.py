"""010 T028 (FR-018): the kill switch stops prod-sim answering with the pilot until a person
releases it with pilot-kill; activating twice is refused; both are recorded."""

import json
from collections.abc import Callable

import pytest

from pilot_tools import cli
from tests.integration.conftest import Host, Packages, serve

INCIDENT = {
    "incident_id": "INC-K-1",
    "title": "VPN down",
    "description": "VPN drops",
    "urgency": "high",
}


def test_kill_switch(host: Callable[[str], Host], packages: Packages) -> None:
    prod = host("prod-sim")
    prod.client.post("/deployments", json={"package_hash": packages.default, "role": "stable"})
    assert prod.client.post("/triage", json=INCIDENT).status_code == 200
    on = prod.client.post("/kill", json={"action": "activate", "reason": "drift"})
    assert on.json() == {"active": True}
    assert prod.client.post("/kill", json={"action": "activate", "reason": "x"}).status_code == 409
    stopped = prod.client.post("/triage", json=INCIDENT)
    assert stopped.status_code == 503 and "kill switch" in stopped.text
    with serve(prod.client.app) as url:  # leaving serve() stops the host's workers
        with pytest.raises(SystemExit) as done:
            cli.kill_main(["release", "--reason", "investigated", "--host", url])
        assert done.value.code in (0, None)
        assert prod.client.post("/triage", json=INCIDENT).status_code == 200
        released = prod.client.post("/kill", json={"action": "release", "reason": "x"})
        assert released.status_code == 409
    kills = [r for r in prod.record("faults") if r["fault"] == "kill_switch"]
    assert [r["action"] for r in kills] == ["activate", "release"]
    assert json.dumps(kills[0]["affected"]).count(packages.default) == 1


def test_kill_switch_only_in_prodsim(host: Callable[[str], Host]) -> None:
    dev = host("dev")
    assert dev.client.post("/kill", json={"action": "activate", "reason": "x"}).status_code == 405
