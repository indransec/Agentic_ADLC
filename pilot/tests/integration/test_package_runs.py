"""T012: a built package, extracted and run as a worker process, answers and reports its hash
(FR-004, SC-002)."""

from pathlib import Path

import httpx

from pilot_tools.build import build, extract
from pilot_tools.workers import start_worker
from tests.conftest import DEFAULT_FILL, TEMPLATE

INCIDENT = {
    "incident_id": "INC-9",
    "title": "Printer jam",
    "affected_service": "printers",
    "description": "The office printer on floor 2 jams on every page.",
    "urgency": "low",
}


def test_package_runs_as_a_worker(tmp_path: Path) -> None:
    built = build(TEMPLATE, DEFAULT_FILL, tmp_path / "registry")
    root = extract(tmp_path / "registry", built.package_hash, tmp_path / "run")
    worker = start_worker("w1", root, built.package_hash, "dev", {})
    try:
        health = httpx.get(f"{worker.url}/health").json()
        assert health["package_hash"] == built.package_hash and health["environment"] == "dev"
        answer = httpx.post(f"{worker.url}/triage", json=INCIDENT).json()
        assert answer["team"] == "end-user-computing" and answer["priority"] == "P4"
    finally:
        worker.stop()
    assert not worker.healthy()
