"""``pilot-host``: one pilot environment (FR-010 to FR-012, FR-015, FR-018 to FR-021; contracts).

Dev and test run one package on request (create, status, tear down). Prod-sim runs a stable and an
optional candidate package behind the splitter, and takes the faults. Every operation is appended
to the environment's JSON Lines records. Packages run as worker processes; no container is created.
"""

import argparse
import contextlib
import itertools
import json
import os
import shutil
import threading
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML

from pilot_tools.build import digest_of, exists, extract
from pilot_tools.split import Mode, chooses_candidate
from pilot_tools.workers import Worker, start_worker

ENVIRONMENTS = ("dev", "test", "prod-sim")
PROD_SIM = "prod-sim"
FAULTS = ("model_swap", "pii_leak")
DEFAULT_SWAP_SHARE = 0.5


class Records:
    """Append-only JSON Lines records (data-model.md)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.lock = threading.Lock()

    def add(self, name: str, **row: Any) -> dict[str, Any]:
        entry = {"at": datetime.now(UTC).isoformat(), **row}
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            with (self.folder / f"{name}.jsonl").open("a") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
        return entry

    def last(self, name: str, n: int = 20) -> list[dict[str, Any]]:
        path = self.folder / f"{name}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()[-n:]]


@dataclass
class Running:
    package_hash: str
    workers: list[Worker]
    settings: dict[str, str]
    root: Path
    timeout_s: float
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    turns: Any = None

    def next_worker(self) -> Worker:
        if self.turns is None:
            self.turns = itertools.cycle(self.workers)
        worker: Worker = next(self.turns)
        return worker

    def stop(self) -> None:
        for worker in self.workers:
            worker.stop()
        shutil.rmtree(self.root, ignore_errors=True)


class Create(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    settings: dict[str, str] = Field(default_factory=dict)


class Deploy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    role: Literal["stable", "candidate"]


class Split(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Mode
    share: float | None = Field(default=None, ge=0, le=1)


class FaultAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["trigger", "revert"]
    parameters: dict[str, float] = Field(default_factory=dict)


def load_definition(template: Path, environment: str) -> dict[str, Any]:
    data: dict[str, Any] = YAML(typ="safe").load(
        (template / "infra" / f"{environment}.yaml").read_text()
    )
    return data


def create_host(
    environment: str, template: Path, registry: Path, work: Path, records_dir: Path
) -> FastAPI:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"unknown environment {environment}")
    records = Records(records_dir)
    lock = threading.RLock()
    counter = itertools.count(1)
    state: dict[str, Any] = {
        "env": None,  # dev and test
        "stable": None,  # prod-sim
        "candidate": None,
        "split": {"mode": "full", "share": 0.0},
        "faults": {},
    }
    counts: Counter[str] = Counter()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for key in ("env", "stable", "candidate"):  # stop every worker on shutdown
            if state[key] is not None:
                state[key].stop()

    app = FastAPI(title=f"pilot-host {environment}", lifespan=lifespan)
    app.state.pilot = state  # the running packages (tests stop a candidate through it)

    def start(package_hash: str, settings: dict[str, str], label: str) -> Running:
        root = work / f"{digest_of(package_hash)[:12]}-{label}-{next(counter)}"
        extract(registry, package_hash, root)
        definition = load_definition(root / "template", environment)
        replicas = int(definition["replicas"])
        workers = [
            start_worker(f"{label}-{n}", root, package_hash, environment, settings)
            for n in range(1, replicas + 1)
        ]
        return Running(
            package_hash, workers, settings, root, float(definition["request_timeout_s"])
        )

    def check_settings(settings: dict[str, str]) -> None:
        allowed = load_definition(template, environment).get("overridable") or {}
        for key, value in settings.items():
            if key not in allowed:
                raise HTTPException(422, f"setting {key} is not declared for {environment}")
            if value not in allowed[key]:
                raise HTTPException(422, f"{key}={value} is not allowed; allowed {allowed[key]}")

    def replica(worker: Worker) -> dict[str, Any]:
        report = worker.health()
        if report is None:
            return {"id": worker.id, "healthy": False, "model": None, "leak": None}
        return {"id": worker.id, "healthy": True, "model": report["model"], "leak": report["leak"]}

    def status_of(running: Running) -> dict[str, Any]:
        return {
            "package_hash": running.package_hash,
            "replicas": [replica(w) for w in running.workers],
            "settings": running.settings,
            "started_at": running.started_at,
        }

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "environment": environment}

    @app.get("/infra")
    def infra() -> dict[str, Any]:
        return {
            "template_version": YAML(typ="safe").load((template / "template.yaml").read_text())[
                "version"
            ],
            "definitions": [load_definition(template, env) for env in ENVIRONMENTS],
        }

    @app.post("/environment", status_code=201)
    def create(body: Create) -> dict[str, Any]:
        if environment == PROD_SIM:
            raise HTTPException(405, "prod-sim runs deployments; use /deployments and /split")
        with lock:

            def refuse(code: int, reason: str) -> HTTPException:
                records.add(
                    "environments",
                    environment=environment,
                    operation="create",
                    package_hash=body.package_hash,
                    settings=body.settings,
                    outcome="refused",
                    reason=reason,
                )
                return HTTPException(code, reason)

            if state["env"] is not None:
                raise refuse(409, f"{environment} already runs {state['env'].package_hash}")
            if not exists(registry, body.package_hash):
                raise refuse(404, f"unknown package {body.package_hash}")
            try:
                check_settings(body.settings)
            except HTTPException as exc:
                raise refuse(exc.status_code, str(exc.detail)) from None
            running_now = start(body.package_hash, body.settings, environment)
            state["env"] = running_now
            records.add(
                "environments",
                environment=environment,
                operation="create",
                package_hash=body.package_hash,
                settings=body.settings,
                outcome="ok",
            )
            return {"environment": environment, **status_of(running_now)}

    @app.get("/environment")
    def environment_status() -> dict[str, Any]:
        running: Running | None = state["env"]
        if running is None:
            records.add(
                "environments",
                environment=environment,
                operation="status",
                package_hash=None,
                outcome="not running",
            )
            raise HTTPException(404, f"no environment is running in {environment}")
        status = {"environment": environment, **status_of(running)}
        records.add(
            "environments",
            environment=environment,
            operation="status",
            package_hash=running.package_hash,
            settings=running.settings,
            outcome="ok",
            healthy=all(r["healthy"] for r in status["replicas"]),
        )
        return status

    @app.delete("/environment", status_code=204)
    def delete() -> Response:
        with lock:
            running: Running | None = state["env"]
            if running is None:
                raise HTTPException(404, f"no environment is running in {environment}")
            running.stop()
            state["env"] = None
            records.add(
                "environments",
                environment=environment,
                operation="delete",
                package_hash=running.package_hash,
                settings=running.settings,
                outcome="ok",
            )
        return Response(status_code=204)

    @app.post("/deployments", status_code=201)
    def deploy(body: Deploy) -> dict[str, Any]:
        if environment != PROD_SIM:
            raise HTTPException(405, "deployments are for prod-sim")
        with lock:
            if not exists(registry, body.package_hash):
                records.add(
                    "splits",
                    operation="deploy",
                    role=body.role,
                    package_hash=body.package_hash,
                    outcome="refused",
                    reason="unknown package",
                )
                raise HTTPException(404, f"unknown package {body.package_hash}")
            previous: Running | None = state[body.role]
            state[body.role] = start(body.package_hash, {}, body.role)
            for fault in state["faults"]:
                apply_fault(fault, state["faults"][fault], [state[body.role]])
            if previous is not None:
                previous.stop()
            records.add(
                "splits",
                operation="deploy",
                role=body.role,
                package_hash=body.package_hash,
                outcome="ok",
            )
            return {"role": body.role, **status_of(state[body.role])}

    def split_view() -> dict[str, Any]:
        stable: Running | None = state["stable"]
        candidate: Running | None = state["candidate"]
        return {
            **state["split"],
            "stable": None if stable is None else stable.package_hash,
            "candidate": None if candidate is None else candidate.package_hash,
        }

    @app.put("/split")
    def set_split(body: Split) -> dict[str, Any]:
        if environment != PROD_SIM:
            raise HTTPException(405, "the split is for prod-sim")
        with lock:
            definition = load_definition(template, environment)
            share = (
                body.share if body.share is not None else definition["splitter"]["default_share"]
            )
            if body.mode != "full" and state["candidate"] is None:
                records.add(
                    "splits",
                    operation="split",
                    mode=body.mode,
                    share=share,
                    outcome="refused",
                    reason="no candidate deployed",
                )
                raise HTTPException(404, "no candidate is deployed")
            if body.mode not in definition["splitter"]["modes"]:
                raise HTTPException(422, f"mode {body.mode} is not allowed")
            state["split"] = {"mode": body.mode, "share": share if body.mode == "canary" else 0.0}
            records.add("splits", operation="split", outcome="ok", **split_view())
            return split_view()

    @app.get("/split")
    def get_split() -> dict[str, Any]:
        deployments = {
            role: status_of(state[role])
            for role in ("stable", "candidate")
            if state[role] is not None
        }
        return {**split_view(), "deployments": deployments, "changes": records.last("splits")}

    def ask(running: Running, incident: dict[str, Any]) -> dict[str, Any]:
        reply = httpx.post(
            f"{running.next_worker().url}/triage", json=incident, timeout=running.timeout_s
        )
        reply.raise_for_status()
        answer: dict[str, Any] = reply.json()
        return answer

    def shadow(candidate: Running, incident: dict[str, Any]) -> None:
        try:
            answer = ask(candidate, incident)
            records.add(
                "shadow",
                request_id=incident.get("incident_id"),
                candidate_hash=candidate.package_hash,
                answer=answer,
            )
        except httpx.HTTPError as exc:
            counts["shadow_failures"] += 1
            records.add(
                "shadow",
                request_id=incident.get("incident_id"),
                candidate_hash=candidate.package_hash,
                error=type(exc).__name__,
            )

    @app.post("/triage")
    def triage(incident: dict[str, Any]) -> dict[str, Any]:
        counts["requests"] += 1
        if environment != PROD_SIM:
            running: Running | None = state["env"]
            if running is None:
                raise HTTPException(404, f"no environment is running in {environment}")
            return ask(running, incident)
        stable: Running | None = state["stable"]
        candidate: Running | None = state["candidate"]
        if stable is None:
            raise HTTPException(404, "no stable package is deployed")
        split = state["split"]
        request_id = str(incident.get("incident_id", ""))
        if candidate is not None and split["mode"] == "shadow":
            threading.Thread(target=shadow, args=(candidate, incident), daemon=True).start()
        if candidate is not None and chooses_candidate(
            split["mode"], split["share"], request_id, True
        ):
            try:
                return ask(candidate, incident)
            except httpx.HTTPError:
                counts["candidate_failures"] += 1
        return ask(stable, incident)

    def apply_fault(
        fault: str, parameters: dict[str, float], targets: list[Running | None]
    ) -> None:
        if fault == "model_swap":
            mode: dict[str, Any] = {
                "model": "degraded",
                "degraded_share": parameters.get("share", DEFAULT_SWAP_SHARE),
            }
        else:
            mode = {"leak": True}
        for running in targets:
            for worker in running.workers if running else []:
                httpx.post(f"{worker.url}/admin/mode", json=mode, timeout=5).raise_for_status()

    def clear_fault(fault: str, targets: list[Running | None]) -> None:
        mode: dict[str, Any] = {"model": "simulated"} if fault == "model_swap" else {"leak": False}
        for running in targets:
            for worker in running.workers if running else []:
                httpx.post(f"{worker.url}/admin/mode", json=mode, timeout=5).raise_for_status()

    @app.post("/faults/{fault}")
    def faults(fault: str, body: FaultAction) -> dict[str, Any]:
        if environment != PROD_SIM:
            raise HTTPException(405, "faults are injected in prod-sim")
        if fault not in FAULTS:
            raise HTTPException(404, f"unknown fault {fault}")
        with lock:
            targets = [state["stable"], state["candidate"]]
            affected = {
                "packages": [r.package_hash for r in targets if r],
                "replicas": [w.id for r in targets if r for w in r.workers],
            }
            active = fault in state["faults"]
            if body.action == "trigger" and active:
                records.add(
                    "faults",
                    fault=fault,
                    action="trigger",
                    parameters=body.parameters,
                    affected=affected,
                    outcome="refused",
                    reason="already active",
                )
                raise HTTPException(409, f"{fault} is already active")
            if body.action == "revert" and not active:
                raise HTTPException(409, f"{fault} is not active")
            if body.action == "trigger":
                apply_fault(fault, body.parameters, targets)
                state["faults"][fault] = body.parameters
            else:
                clear_fault(fault, targets)
                state["faults"].pop(fault)
            return records.add(
                "faults",
                fault=fault,
                action=body.action,
                parameters=body.parameters,
                affected=affected,
                outcome="ok",
            )

    @app.get("/faults")
    def list_faults() -> dict[str, Any]:
        return {"active": state["faults"], "records": records.last("faults")}

    def collect(role: str, running: Running) -> dict[str, Any]:
        """The replicas' own metrics, summed per package (FR-005)."""
        totals: Counter[str] = Counter()
        cost, fallbacks, unreachable = 0.0, 0, 0
        p95: list[float] = []
        for worker in running.workers:
            report = worker.metrics()
            if report is None:
                unreachable += 1
                continue
            totals.update(report["counts"])
            cost += float(report.get("cost", 0.0))
            fallbacks += int(report.get("real_fallbacks", 0))
            if report.get("latency_p95_ms") is not None:
                p95.append(float(report["latency_p95_ms"]))
        return {
            "role": role,
            "package_hash": running.package_hash,
            "replicas": len(running.workers),
            "unreachable": unreachable,
            "counts": dict(totals),
            "cost": round(cost, 6),
            "real_fallbacks": fallbacks,
            "latency_p95_ms_worst_replica": max(p95) if p95 else None,
        }

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        roles = ("env",) if environment != PROD_SIM else ("stable", "candidate")
        packages = [collect(role, state[role]) for role in roles if state[role] is not None]
        return {"environment": environment, "counts": dict(counts), "packages": packages}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(prog="pilot-host", description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PILOT_HOST_PORT", "8100")))
    args = parser.parse_args()
    app = create_host(
        args.env,
        Path(os.environ.get("PILOT_TEMPLATE", "template")),
        Path(os.environ.get("PILOT_REGISTRY", "/packages")),
        Path(os.environ.get("PILOT_WORK", "/tmp/pilot-work")),  # noqa: S108 - container scratch
        Path(os.environ.get("PILOT_RECORDS", "/records")),
    )
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_config=None)  # noqa: S104 - pilot net
