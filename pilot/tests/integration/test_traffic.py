"""T020: the traffic generator holds its rate, pauses, counts, and measures routing accuracy and
personal-data leaks against the expected answers (US4; FR-014, FR-016, SC-004)."""

import time
from collections.abc import Callable

from pilot_tools.traffic import Traffic
from tests.integration.conftest import Host, Packages, serve


def test_rate_counts_accuracy_and_pause(host: Callable[[str], Host], packages: Packages) -> None:
    h = host("prod-sim")
    h.client.post("/deployments", json={"package_hash": packages.default, "role": "stable"})
    with serve(h.client.app) as url:
        traffic = Traffic(url, seed=9, size=200, pii_share=0.2, rate=20.0, timeout_s=5)
        traffic.start()
        time.sleep(3.0)
        traffic.pause()
        time.sleep(0.5)
        first = traffic.metrics()
        time.sleep(0.5)
        assert traffic.metrics()["sent"] == first["sent"]  # paused: nothing new
        traffic.stop()
    assert 0.9 * 60 <= first["sent"] <= 1.1 * 60  # 20 per second for 3 s, within ±10%
    assert first["answered"] == first["sent"] and first["failed"] == first["timed_out"] == 0
    assert first["routing_accuracy"] >= 0.9
    assert first["pii_leak_rate"] == 0.0
    assert set(first["by_package"]) == {packages.default}


def test_leaks_and_timeouts_are_counted(host: Callable[[str], Host], packages: Packages) -> None:
    h = host("prod-sim")
    h.client.post("/deployments", json={"package_hash": packages.default, "role": "stable"})
    h.client.post("/faults/pii_leak", json={"action": "trigger"})
    with serve(h.client.app) as url:
        traffic = Traffic(url, seed=4, size=100, pii_share=0.5, rate=20.0, timeout_s=5)
        traffic.start()
        time.sleep(2.0)
        traffic.stop()
        leaked = traffic.metrics()
    assert leaked["pii_leak_rate"] >= 0.1
    slow = Traffic("http://127.0.0.1:9", seed=1, size=10, rate=10.0, timeout_s=0.2)
    slow.start()
    time.sleep(1.0)
    slow.stop()
    counts = slow.metrics()
    assert counts["sent"] > 0 and counts["failed"] + counts["timed_out"] == counts["sent"]
