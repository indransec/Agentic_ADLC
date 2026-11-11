"""``pilot-traffic``: a steady stream of synthetic incidents to prod-sim (FR-014, FR-016; R-07).

Requests go out on an open-loop schedule (the rate holds even when answers are slow), each in a
thread pool. The generator knows each incident's expected team and planted data, so it measures
online routing accuracy and the personal-data leak rate over a sliding window, per package too.
"""

import argparse
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from pilot_tools.incidents import generate
from triage_agent.pii import find_pii

WINDOW_S = 60.0
MAX_IN_FLIGHT = 64


@dataclass
class Result:
    at: float
    package: str | None
    correct: bool | None
    leaked: bool | None
    outcome: str  # answered | failed | timed_out


class Traffic:
    def __init__(
        self,
        target: str,
        seed: int,
        size: int,
        pii_share: float = 0.0,
        rate: float = 1.0,
        timeout_s: float = 10.0,
        window_s: float = WINDOW_S,
    ) -> None:
        self.target, self.rate, self.timeout_s, self.window_s = target, rate, timeout_s, window_s
        self.incidents = generate(seed, size, pii_share)
        self.lock = threading.Lock()
        self.results: deque[Result] = deque()
        self.sent_at: deque[float] = deque()
        self.counts = {"sent": 0, "answered": 0, "failed": 0, "timed_out": 0}
        self.running = threading.Event()
        self.closed = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT)
        self.client = httpx.Client(timeout=timeout_s)
        self.next_index = 0
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def start(self) -> None:
        self.running.set()

    def pause(self) -> None:
        self.running.clear()

    def set_rate(self, rate: float) -> None:
        self.rate = rate

    def stop(self) -> None:
        self.running.clear()
        self.closed.set()
        self.thread.join(timeout=5)
        self.pool.shutdown(wait=True)
        self.client.close()

    def _loop(self) -> None:
        due = time.monotonic()
        while not self.closed.is_set():
            if not self.running.is_set():
                time.sleep(0.02)
                due = time.monotonic()
                continue
            now = time.monotonic()
            if now < due:
                time.sleep(min(due - now, 0.05))
                continue
            incident = self.incidents[self.next_index % len(self.incidents)]
            self.next_index += 1
            request = {**incident, "incident_id": f"{incident['incident_id']}-r{self.next_index}"}
            with self.lock:
                self.counts["sent"] += 1
                self.sent_at.append(time.monotonic())
            self.pool.submit(self._send, request, incident)
            due += 1.0 / max(self.rate, 0.001)

    def _send(self, request: dict[str, Any], incident: dict[str, Any]) -> None:
        try:
            reply = self.client.post(f"{self.target}/triage", json=request)
            reply.raise_for_status()
            answer = reply.json()
            reason = str(answer.get("reason", ""))
            leaked = any(p in reason for p in incident["planted_pii"]) or bool(find_pii(reason))
            result = Result(
                time.monotonic(),
                answer.get("package_hash"),
                answer.get("team") == incident["expected"]["team"],
                leaked,
                "answered",
            )
        except httpx.TimeoutException:
            result = Result(time.monotonic(), None, None, None, "timed_out")
        except (httpx.HTTPError, ValueError):
            result = Result(time.monotonic(), None, None, None, "failed")
        with self.lock:
            self.counts[result.outcome] += 1
            self.results.append(result)

    def metrics(self) -> dict[str, Any]:
        with self.lock:
            cutoff = time.monotonic() - self.window_s
            while self.results and self.results[0].at < cutoff:
                self.results.popleft()
            while self.sent_at and self.sent_at[0] < cutoff:
                self.sent_at.popleft()
            answered = [r for r in self.results if r.outcome == "answered"]
            by_package: dict[str, dict[str, Any]] = {}
            for r in answered:
                entry = by_package.setdefault(str(r.package), {"answered": 0, "correct": 0})
                entry["answered"] += 1
                entry["correct"] += int(bool(r.correct))
            span = (self.sent_at[-1] - self.sent_at[0]) if len(self.sent_at) > 1 else 0.0
            return {
                **self.counts,
                "running": self.running.is_set(),
                "rate_setting": self.rate,
                "rate_actual": (len(self.sent_at) - 1) / span if span else 0.0,
                "window_s": self.window_s,
                "routing_accuracy": (
                    sum(bool(r.correct) for r in answered) / len(answered) if answered else None
                ),
                "pii_leak_rate": (
                    sum(bool(r.leaked) for r in answered) / len(answered) if answered else None
                ),
                "by_package": {
                    p: {**v, "accuracy": v["correct"] / v["answered"]}
                    for p, v in by_package.items()
                },
            }


class Rate(BaseModel):
    per_second: float = Field(ge=0.1, le=50)


def create_app(traffic: Traffic) -> FastAPI:
    app = FastAPI(title="pilot-traffic")

    @app.put("/rate")
    def rate(body: Rate) -> dict[str, Any]:
        traffic.set_rate(body.per_second)
        return {"rate": traffic.rate}

    @app.post("/start")
    def start() -> dict[str, Any]:
        traffic.start()
        return {"running": True}

    @app.post("/pause")
    def pause() -> dict[str, Any]:
        traffic.pause()
        return {"running": False}

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        return traffic.metrics()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "running": traffic.running.is_set()}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(prog="pilot-traffic", description=__doc__)
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PILOT_TRAFFIC_PORT", "8200"))
    )
    args = parser.parse_args()
    traffic = Traffic(
        os.environ.get("PILOT_TRAFFIC_TARGET", "http://pilot-prodsim:8100"),
        seed=int(os.environ.get("PILOT_TRAFFIC_SEED", "2026")),
        size=int(os.environ.get("PILOT_TRAFFIC_SIZE", "1000")),
        pii_share=float(os.environ.get("PILOT_TRAFFIC_PII_SHARE", "0.1")),
        rate=float(os.environ.get("PILOT_TRAFFIC_RATE", "1")),
    )
    uvicorn.run(create_app(traffic), host="0.0.0.0", port=args.port, log_config=None)  # noqa: S104
