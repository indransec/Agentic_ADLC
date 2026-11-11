"""T008: the agent app answers, reports its package, counts, and switches modes for faults; the
real model falls back to the simulated one on a bad or failed reply (FR-005, FR-006)."""

import json
import shutil
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_FILL, TEMPLATE
from triage_agent.app import create_app
from triage_agent.fill import load_fill
from triage_agent.real import RealModel
from triage_agent.reference import Reference
from triage_agent.triage import Incident

INCIDENT = {
    "incident_id": "INC-1",
    "title": "VPN drops",
    "affected_service": "vpn",
    "urgency": "medium",
    "description": "VPN drops every few minutes. Mail me at ann.example@example.com",
}


def package(tmp_path: Path) -> Path:
    root = tmp_path / "pkg"
    shutil.copytree(TEMPLATE, root / "template")
    shutil.copytree(DEFAULT_FILL, root / "fill")
    return root


def test_triage_health_metrics_and_modes(tmp_path: Path) -> None:
    client = TestClient(create_app(package(tmp_path), "sha256:" + "a" * 64))
    health = client.get("/health").json()
    assert health["package_hash"] == "sha256:" + "a" * 64 and health["model"] == "simulated"
    answer = client.post("/triage", json=INCIDENT).json()
    assert answer["team"] == "network-ops" and answer["package_hash"] == health["package_hash"]
    assert "ann.example" not in answer["reason"]
    assert client.post("/admin/mode", json={"leak": True}).json()["leak"] is True
    leaked = client.post("/triage", json=INCIDENT).json()
    assert "ann.example@example.com" in leaked["reason"]
    client.post("/admin/mode", json={"model": "degraded", "degraded_share": 1.0, "leak": False})
    assert client.post("/triage", json=INCIDENT).json()["team"] != "network-ops"
    assert client.post("/admin/mode", json={"model": "real"}).status_code == 422
    counts = client.get("/metrics").json()["counts"]
    assert counts["requests"] == 3 and counts["pii_outputs"] == 1


def reply(content: Any, status: int = 200) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        body = {
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"total_tokens": 321},
        }
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handle)


def real(transport: httpx.MockTransport) -> RealModel:
    return RealModel(
        load_fill(TEMPLATE, DEFAULT_FILL),
        Reference.load(TEMPLATE),
        "http://m/v1",
        "k",
        ["access", "hardware", "software", "network", "security"],
        client=httpx.Client(transport=transport),
    )


def test_real_model_answer_and_fallbacks() -> None:
    incident = Incident(**INCIDENT)
    good = real(
        reply(
            {
                "category": "network",
                "priority": "P2",
                "team": "network-ops",
                "reason": "VPN is owned by network ops",
                "review": False,
            }
        )
    )
    answer = good.triage(incident)
    assert (answer.model, answer.team, answer.tokens) == ("real", "network-ops", 321)
    invented = real(
        reply({"category": "network", "priority": "P2", "team": "astronauts", "reason": "x"})
    )
    assert invented.triage(incident).model == "simulated" and invented.fallbacks == 1
    failed = real(reply({}, status=503))
    assert failed.triage(incident).team == "network-ops" and failed.fallbacks == 1
