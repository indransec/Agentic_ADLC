"""The pilot's app: one package, served by a worker process (FR-001, FR-004, FR-005).

``create_app(root)`` reads the package folder (``template/`` and ``fill/``) and the settings the
environment host passes in ``PILOT_*`` variables. ``/admin/mode`` is the local hook the host uses
for faults; workers listen on 127.0.0.1 only.
"""

import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from triage_agent import telemetry
from triage_agent.fill import load_fill, template_spec
from triage_agent.pii import find_pii
from triage_agent.rai import jailbreak_count, toxic_count
from triage_agent.real import RealModel
from triage_agent.reference import Reference
from triage_agent.triage import Assignment, DegradedModel, Incident, SimulatedModel, leak


class Mode(BaseModel):
    model: Literal["simulated", "degraded", "real"] | None = None
    degraded_share: float | None = None
    leak: bool | None = None


def create_app(root: Path, package_hash: str | None = None) -> FastAPI:
    template, fill_dir = root / "template", root / "fill"
    fill = load_fill(template, fill_dir)
    reference = Reference.load(template)
    package = package_hash or os.environ.get("PILOT_PACKAGE_HASH", "unknown")
    environment = os.environ.get("PILOT_ENVIRONMENT", "local")
    telemetry.setup(environment, os.environ.get("PILOT_OTLP_ENDPOINT"))
    simulated = SimulatedModel(fill, reference)
    real: RealModel | None = None
    mode_name = os.environ.get("PILOT_MODEL_MODE", fill.settings.model_mode)
    if mode_name == "real":
        real = RealModel(
            fill,
            reference,
            os.environ.get("PILOT_MODEL_URL", "https://api.openai.com/v1"),
            os.environ.get("PILOT_MODEL_API_KEY", ""),
            list(template_spec(template)["categories"]),
        )
    price = float(os.environ.get("PILOT_MODEL_PRICE_PER_1K_TOKENS") or 0)
    state: dict[str, Any] = {"model": mode_name, "degraded_share": 0.5, "leak": False}
    cost = {"total": 0.0}  # only the real model costs anything (FR-005)
    counts: Counter[str] = Counter()
    latency_ms: list[float] = []
    app = FastAPI(title="Incident Triage Assistant", version=str(package))

    def current() -> Any:
        if state["model"] == "degraded":
            return DegradedModel(simulated, float(state["degraded_share"]))
        if state["model"] == "real" and real is not None:
            return real
        return simulated

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "package_hash": package,
            "environment": environment,
            "model": state["model"],
            "leak": state["leak"],
        }

    @app.post("/triage")
    def triage(incident: Incident) -> dict[str, Any]:
        started = time.perf_counter()
        with telemetry.tracer().start_as_current_span("triage.request") as span:
            span.set_attribute("request_id", incident.incident_id)
            span.set_attribute("package_hash", package)

            def on_tool(name: str) -> None:
                with telemetry.tracer().start_as_current_span("triage.tool") as tool_span:
                    tool_span.set_attribute("tool", name)
                    tool_span.set_attribute("request_id", incident.incident_id)

            model = current()
            with telemetry.tracer().start_as_current_span("triage.model") as model_span:
                model_span.set_attribute("model", model.name)
                answer: Assignment = model.triage(incident, on_tool)
            if state["leak"]:
                answer = leak(answer, incident)
            span.set_attribute("team", answer.team)
        counts["requests"] += 1
        counts[f"team:{answer.team}"] += 1
        counts["jailbreak_attempts"] += jailbreak_count(incident.description)
        counts["toxic_outputs"] += toxic_count(answer.reason)
        counts["pii_outputs"] += bool(find_pii(answer.reason))
        counts["tokens"] += answer.tokens
        if answer.model == "real":
            cost["total"] += answer.tokens * price / 1000
        latency_ms.append((time.perf_counter() - started) * 1000)
        return {**answer.model_dump(), "package_hash": package}

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        recent = sorted(latency_ms[-1000:])
        return {
            "package_hash": package,
            "counts": dict(counts),
            "cost": round(cost["total"], 6),
            "real_fallbacks": 0 if real is None else real.fallbacks,
            "latency_p95_ms": recent[int(len(recent) * 0.95)] if recent else None,
        }

    @app.post("/admin/mode")
    def admin_mode(mode: Mode) -> dict[str, Any]:
        if mode.model == "real" and real is None:
            raise HTTPException(422, "the real model is not configured for this worker")
        for key, value in mode.model_dump(exclude_none=True).items():
            state[key] = value
        return dict(state)

    return app


def factory() -> FastAPI:
    """Uvicorn factory: the package folder is ``PILOT_PACKAGE_ROOT``."""
    return create_app(Path(os.environ["PILOT_PACKAGE_ROOT"]))
