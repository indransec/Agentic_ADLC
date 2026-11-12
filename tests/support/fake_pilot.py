"""A fake pilot for the platform's bridge tests (feature 010): the HTTP contract of feature 009's
hosts, traffic generator and this feature's pilot additions (``pilot-lab``, kill switch, feedback),
in memory. The platform never imports pilot code; the pilot's own suite tests the real thing.

One app serves every pilot service under a prefix: ``/dev``, ``/test``, ``/prodsim``, ``/lab``,
``/traffic``.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Response

from adlc.tools.bridge.pilot import PilotUrls

TEAMS = ("service-desk", "identity-access", "network-ops", "security-ops")
LAYOUT = ("instructions.md", "routing_rules.yaml", "settings.yaml")
EXAMPLE = {
    "instructions.md": "Route incidents.",
    "routing_rules.yaml": "a: 1",
    "settings.yaml": "model_mode: simulated",
}
EMAIL = re.compile(r"[\w.+-]+@example\.com")
SLICES = [{"name": "p1", "field": "priority", "value": "P1"}]


def package_hash(files: dict[str, str]) -> str:
    body = json.dumps(files, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _rows(dataset: str, size: int, pii: bool) -> list[dict[str, Any]]:
    rows = []
    for n in range(1, size + 1):
        team = TEAMS[n % len(TEAMS)]
        priority = "P1" if n % 5 == 0 else "P3"
        planted = [f"person{n}@example.com"] if pii else []
        description = f"Problem {n} with a service." + (
            f" Reach me at {planted[0]}." if pii else ""
        )
        rows.append(
            {
                "incident_id": f"INC-{dataset}-{n}",
                "title": f"Problem {n}",
                "description": description,
                "reporter": {"name": "Synthetic Person", "department": "Ops", "persona": "staff"},
                "affected_service": f"svc-{n % 7}",
                "urgency": "medium",
                "edge_case": "none",
                "expected": {"team": team, "category": "software", "priority": priority},
                "synthetic": True,
                "planted_pii": planted,
            }
        )
    return rows


DATASETS: dict[str, dict[str, Any]] = {
    "golden": {"version": "1.0.0", "seed": 7, "size": 20, "pii_share": 0.0},
    "pii": {"version": "1.0.0", "seed": 5, "size": 10, "pii_share": 1.0},
}


@dataclass
class Host:
    environment: str
    running: dict[str, Any] | None = None
    mode: str = "good"  # good, degraded, leak, obedient
    killed: bool = False
    stable: str | None = None
    candidate: str | None = None
    split: dict[str, Any] = field(default_factory=lambda: {"mode": "full", "share": 0.0})
    counts: dict[str, int] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)


@dataclass
class FakePilot:
    packages: dict[str, dict[str, Any]] = field(default_factory=dict)
    hosts: dict[str, Host] = field(
        default_factory=lambda: {e: Host(e) for e in ("dev", "test", "prod-sim")}
    )
    rows: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {
            k: _rows(k, int(v["size"]), float(v["pii_share"]) > 0) for k, v in DATASETS.items()
        }
    )
    traffic: dict[str, Any] = field(
        default_factory=lambda: {"routing_accuracy": 0.97, "pii_leak_rate": 0.0}
    )
    builds: list[dict[str, str]] = field(default_factory=list)

    def add_package(self, files: dict[str, str] | None = None) -> str:
        files = files or {"routing_rules.yaml": "a: 1", "instructions.md": "Route incidents."}
        digest = package_hash(files)
        self.packages[digest] = {"package_hash": digest, "template_id": "fake", "files": files}
        return digest

    # -------------------------------------------------------------- answers

    def expected(self, incident_id: str) -> dict[str, Any] | None:
        base = incident_id.split("~")[0]
        for rows in self.rows.values():
            for row in rows:
                if row["incident_id"] == base:
                    return dict(row["expected"])
        return None

    def answer(self, host: Host, incident: dict[str, Any], package: str) -> dict[str, Any]:
        expected = self.expected(str(incident.get("incident_id", ""))) or {
            "team": TEAMS[0],
            "category": "software",
            "priority": "P3",
        }
        n = int(re.sub(r"\D", "", str(incident.get("incident_id", ""))) or 0)
        team = expected["team"]
        if host.mode == "degraded" and n % 2 == 0:
            team = "wrong-team"
        reason = "Routed by the catalogue."
        description = str(incident.get("description", ""))
        if host.mode == "leak":
            reason += " Contact: " + ", ".join(EMAIL.findall(description))
        if host.mode == "obedient" and "CANARY" in description:
            reason += " CANARY-7731"
        if "useless" in description.lower():
            host.counts["jailbreak_attempts"] = host.counts.get("jailbreak_attempts", 0) + 1
        host.counts["requests"] = host.counts.get("requests", 0) + 1
        host.counts["tokens"] = host.counts.get("tokens", 0) + 50
        return {
            "incident_id": incident.get("incident_id"),
            "team": team,
            "category": expected["category"],
            "priority": expected["priority"],
            "reason": reason,
            "review": False,
            "package_hash": package,
            "model": "degraded" if host.mode == "degraded" else "simulated",
            "tokens": 50,
        }

    # -------------------------------------------------------------- app

    def app(self) -> FastAPI:
        app = FastAPI()
        for prefix, environment in (("/dev", "dev"), ("/test", "test"), ("/prodsim", "prod-sim")):
            app.include_router(self._host(self.hosts[environment]), prefix=prefix)
        app.include_router(self._lab(), prefix="/lab")
        app.include_router(self._traffic(), prefix="/traffic")
        app.include_router(self._jaeger(), prefix="/jaeger")
        return app

    def _jaeger(self) -> APIRouter:
        r = APIRouter()

        @r.get("/api/v3/traces")
        def traces() -> dict[str, Any]:
            def attr(key: str, value: str) -> dict[str, Any]:
                return {"key": key, "value": {"stringValue": value}}

            spans = [
                {
                    "traceId": f"t{n}",
                    "name": "triage.request",
                    "startTimeUnixNano": "1000000",
                    "endTimeUnixNano": "4000000",
                    "status": {"code": "ok"},
                    "attributes": [
                        attr("request_id", f"INC-{n}"),
                        attr("package_hash", "sha256:" + "a" * 64),
                        attr("description", "Reach me at secret@example.com"),
                        attr("reason", "Contact: secret@example.com"),
                    ],
                }
                for n in (1, 2)
            ]
            return {"result": {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}}

        return r

    def _host(self, host: Host) -> APIRouter:
        r = APIRouter()

        @r.get("/health")
        def health() -> dict[str, Any]:
            return {"status": "ok", "environment": host.environment}

        @r.get("/infra")
        def infra() -> dict[str, Any]:
            return {
                "template_id": "incident-triage",
                "template_version": "1.0.0",
                "definitions": [
                    {"environment": e, "version": "1.0.0", "replicas": 1}
                    for e in ("dev", "test", "prod-sim")
                ],
            }

        @r.post("/environment", status_code=201)
        def create(body: dict[str, Any]) -> dict[str, Any]:
            host.calls.append("create")
            if host.environment == "prod-sim":
                raise HTTPException(405, "prod-sim runs deployments")
            if host.running is not None:
                raise HTTPException(409, f"{host.environment} already runs a package")
            if body["package_hash"] not in self.packages:
                raise HTTPException(404, f"unknown package {body['package_hash']}")
            if set(body.get("settings") or {}) - {"model_mode"}:
                raise HTTPException(422, "setting is not declared")
            host.running = {
                "environment": host.environment,
                "package_hash": body["package_hash"],
                "replicas": [
                    {
                        "id": f"{host.environment}-1",
                        "healthy": True,
                        "model": "simulated",
                        "leak": False,
                    }
                ],
                "settings": body.get("settings") or {},
                "started_at": "2026-11-12T10:00:00+00:00",
            }
            return host.running

        @r.get("/environment")
        def status() -> dict[str, Any]:
            if host.running is None:
                raise HTTPException(404, "no environment is running")
            return host.running

        @r.delete("/environment", status_code=204)
        def delete() -> Response:
            host.calls.append("delete")
            if host.running is None:
                raise HTTPException(404, "no environment is running")
            host.running = None
            return Response(status_code=204)

        @r.post("/triage")
        def triage(incident: dict[str, Any]) -> dict[str, Any]:
            if host.killed:
                raise HTTPException(503, "stopped by the kill switch")
            if host.environment != "prod-sim":
                if host.running is None:
                    raise HTTPException(404, "no environment is running")
                return self.answer(host, incident, host.running["package_hash"])
            if host.stable is None:
                raise HTTPException(404, "no stable package is deployed")
            return self.answer(host, incident, host.stable)

        @r.get("/metrics")
        def metrics() -> dict[str, Any]:
            package = (host.running or {}).get("package_hash") or host.stable
            return {
                "environment": host.environment,
                "counts": {"requests": host.counts.get("requests", 0)},
                "packages": [
                    {
                        "role": "env",
                        "package_hash": package,
                        "counts": dict(host.counts),
                        "cost": 0.0,
                        "latency_p95_ms_worst_replica": 3.0,
                    }
                ]
                if package
                else [],
            }

        @r.post("/deployments", status_code=201)
        def deploy(body: dict[str, Any]) -> dict[str, Any]:
            if body["package_hash"] not in self.packages:
                raise HTTPException(404, "unknown package")
            setattr(host, body["role"], body["package_hash"])
            return {"role": body["role"], "package_hash": body["package_hash"]}

        @r.put("/split")
        def set_split(body: dict[str, Any]) -> dict[str, Any]:
            if body["mode"] != "full" and host.candidate is None:
                raise HTTPException(404, "no candidate is deployed")
            share = body.get("share", 0.2) if body["mode"] == "canary" else 0.0
            host.split = {"mode": body["mode"], "share": share}
            return {**host.split, "stable": host.stable, "candidate": host.candidate}

        @r.get("/split")
        def get_split() -> dict[str, Any]:
            return {**host.split, "stable": host.stable, "candidate": host.candidate}

        @r.post("/kill")
        def kill(body: dict[str, Any]) -> dict[str, Any]:
            if body["action"] == "activate" and host.killed:
                raise HTTPException(409, "the kill switch is already active")
            host.killed = body["action"] == "activate"
            return {"active": host.killed}

        return r

    def _lab(self) -> APIRouter:
        r = APIRouter()

        @r.get("/layout")
        def get_layout() -> dict[str, Any]:
            return {
                "files": list(LAYOUT),
                "example": dict(EXAMPLE),
                "template_id": "incident-triage",
                "template_version": "1.0.0",
            }

        @r.post("/build")
        def build(body: dict[str, Any]) -> dict[str, Any]:
            files = {str(k): str(v) for k, v in body["files"].items()}
            self.builds.append(files)
            if not files.get("routing_rules.yaml", "").strip():
                return {
                    "checks": [
                        {"name": "validate", "passed": False, "detail": "routing_rules: missing"}
                    ]
                }
            digest = self.add_package(files)
            checks = [
                {"name": n, "passed": True, "detail": ""}
                for n in (
                    "validate",
                    "build",
                    "reproducible",
                    "smoke",
                    "tests",
                    "sast",
                    "secret_scan",
                    "sbom",
                    "observability",
                )
            ]
            secret = "api_key" in files.get("instructions.md", "")
            if secret:
                checks[6]["passed"] = False
            report = {
                "tests": {
                    "package": {
                        "total_count": 25,
                        "passed_count": 25,
                        "failed_count": 0,
                        "coverage_pct": 86.2,
                    }
                },
                "scans": {
                    "sast": {"critical_count": 0, "high_count": 0, "medium_count": 0},
                    "secret_scan": {
                        "critical_count": 0,
                        "high_count": int(secret),
                        "medium_count": 0,
                    },
                },
                "sbom": {"generated": True, "licences_approved": True, "components": []},
                "observability": [
                    {"signal": "traces", "emitting": True, "sample_trace_id": "INC-1-1"},
                    {"signal": "rai_metrics", "emitting": True, "sample_trace_id": "INC-1-1"},
                ],
            }
            return {"checks": checks, **report, **({} if secret else {"package_hash": digest})}

        @r.get("/packages/{digest}")
        def manifest(digest: str) -> dict[str, Any]:
            if digest not in self.packages:
                raise HTTPException(404, "unknown package")
            return self.packages[digest]

        @r.get("/datasets")
        def datasets() -> list[dict[str, Any]]:
            return [
                {
                    "id": k,
                    **v,
                    "sha256": "sha256:" + hashlib.sha256(k.encode()).hexdigest(),
                    "scored_fields": ["team", "category", "priority"],
                    "slices": SLICES,
                }
                for k, v in DATASETS.items()
            ]

        @r.get("/datasets/{dataset}")
        def dataset(dataset: str) -> dict[str, Any]:
            if dataset not in self.rows:
                raise HTTPException(404, "unknown dataset")
            meta = next(d for d in datasets() if d["id"] == dataset)
            return {"dataset": meta, "rows": self.rows[dataset]}

        return r

    def _traffic(self) -> APIRouter:
        r = APIRouter()

        @r.get("/metrics")
        def metrics() -> dict[str, Any]:
            return {
                "sent": 100,
                "answered": 100,
                "failed": 0,
                "timed_out": 0,
                "rate_actual": 5.0,
                "window_s": 60,
                **self.traffic,
                "by_package": {
                    "sha256:" + "a" * 64: {
                        "answered": 100,
                        "accuracy": self.traffic["routing_accuracy"],
                    }
                },
            }

        @r.get("/feedback")
        def feedback(limit: int = 20) -> dict[str, Any]:
            return {
                "synthetic": True,
                "feedback": [{"rating": 4, "comment": "Routed well", "synthetic": True}][:limit],
            }

        return r


def urls(base: str) -> PilotUrls:
    return PilotUrls(
        f"{base}/dev", f"{base}/test", f"{base}/prodsim", f"{base}/lab", f"{base}/traffic"
    )
