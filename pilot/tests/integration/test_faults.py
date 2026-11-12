"""T022: the model swap and the personal-data leak, on demand, recorded and revertible (US5;
FR-015, FR-016, SC-005, SC-006)."""

import time
from collections.abc import Callable
from typing import Any

from pilot_tools.traffic import Traffic
from tests.integration.conftest import Host, Packages, serve


def run(traffic: Traffic, seconds: float) -> dict[str, Any]:
    traffic.start()
    time.sleep(seconds)
    traffic.pause()
    time.sleep(0.3)
    return traffic.metrics()


def test_model_swap_lowers_accuracy_and_revert_restores_it(
    host: Callable[[str], Host], packages: Packages
) -> None:
    h = host("prod-sim")
    h.client.post("/deployments", json={"package_hash": packages.default, "role": "stable"})
    with serve(h.client.app) as url:
        before = Traffic(url, seed=21, size=300, rate=40.0, window_s=30)
        baseline = run(before, 2.0)["routing_accuracy"]
        before.stop()
        swapped = h.client.post(
            "/faults/model_swap", json={"action": "trigger", "parameters": {"share": 0.5}}
        )
        assert swapped.status_code == 200
        assert h.client.post("/faults/model_swap", json={"action": "trigger"}).status_code == 409
        replicas = h.client.get("/split").json()["deployments"]["stable"]["replicas"]
        assert {r["model"] for r in replicas} == {"degraded"}  # T031: the swap is visible
        during = Traffic(url, seed=21, size=300, rate=40.0, window_s=30)
        degraded = run(during, 2.0)["routing_accuracy"]
        during.stop()
        assert h.client.post("/faults/model_swap", json={"action": "revert"}).status_code == 200
        after = Traffic(url, seed=21, size=300, rate=40.0, window_s=30)
        restored = run(after, 2.0)["routing_accuracy"]
        after.stop()
    assert baseline >= 0.9
    assert baseline - degraded >= 0.3  # the configured margin
    assert abs(restored - baseline) <= 0.05
    actions = [(r["fault"], r["action"], r["outcome"]) for r in h.record("faults")]
    assert actions == [
        ("model_swap", "trigger", "ok"),
        ("model_swap", "trigger", "refused"),
        ("model_swap", "revert", "ok"),
    ]
    first = h.record("faults")[0]
    assert first["parameters"] == {"share": 0.5}
    assert first["affected"]["packages"] == [packages.default]
    assert len(first["affected"]["replicas"]) == 2


def test_pii_leak_is_detected_and_reverted(host: Callable[[str], Host], packages: Packages) -> None:
    h = host("prod-sim")
    h.client.post("/deployments", json={"package_hash": packages.default, "role": "stable"})
    with serve(h.client.app) as url:
        h.client.post("/faults/pii_leak", json={"action": "trigger"})
        leaking = Traffic(url, seed=33, size=200, pii_share=0.3, rate=40.0)
        leaked = run(leaking, 2.0)["pii_leak_rate"]
        leaking.stop()
        h.client.post("/faults/pii_leak", json={"action": "revert"})
        clean = Traffic(url, seed=33, size=200, pii_share=0.3, rate=40.0)
        after = run(clean, 2.0)["pii_leak_rate"]
        clean.stop()
    assert leaked >= 0.1 and after == 0.0
    assert h.client.post("/faults/pii_leak", json={"action": "revert"}).status_code == 409
    assert h.client.get("/faults").json()["active"] == {}


def test_faults_only_in_prodsim_and_known(host: Callable[[str], Host]) -> None:
    dev = host("dev")
    assert dev.client.post("/faults/model_swap", json={"action": "trigger"}).status_code == 405
    prod = host("prod-sim")
    assert prod.client.post("/faults/flood", json={"action": "trigger"}).status_code == 404
