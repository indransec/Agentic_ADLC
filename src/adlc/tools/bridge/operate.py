"""``observability``, ``monitoring`` and ``feedback`` (feature 010 US5; FR-019 to FR-021;
research R-11).

Metrics come from the traffic generator (accuracy and leak rate over its window) and prod-sim's
hosts (cost, latency, RAI counts per package), flattened into one set of named metrics that
monitors evaluate. Traces come from Jaeger's v3 API and keep only allowlisted attributes, so no
incident text or personal data leaves. Monitors are per use case, evaluated in the background and
on read; a breach is recorded once per episode, with value and time, and re-arms after recovery.
"""

import operator
import threading
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import anyio.to_thread

from adlc.tools.bridge.pilot import Pilot
from adlc.tools.bridge.records import Records
from adlc.tools.mcp_app import Call, Handler, ToolFailure

SPAN_ATTRIBUTES = ("request_id", "package_hash", "model", "tool")
OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
TRAFFIC_METRICS = (
    "routing_accuracy",
    "pii_leak_rate",
    "rate_actual",
    "sent",
    "answered",
    "failed",
    "timed_out",
)
HOST_COUNTS = ("toxic_outputs", "pii_outputs", "jailbreak_attempts", "tokens", "requests")


class Telemetry:
    def __init__(self, pilot: Pilot, jaeger_url: str, service: str) -> None:
        self.pilot, self.jaeger_url, self.service = pilot, jaeger_url.rstrip("/"), service

    def metrics(self) -> dict[str, Any]:
        traffic = self.pilot.request("GET", self.pilot.urls.traffic, "/metrics")
        hosts = self.pilot.request("GET", self.pilot.urls.prodsim, "/metrics")
        packages = []
        for p in hosts.get("packages") or []:
            counts = p.get("counts") or {}
            packages.append(
                {
                    "role": p.get("role"),
                    "package_hash": p.get("package_hash"),
                    "cost": p.get("cost", 0.0),
                    "latency_p95_ms": p.get("latency_p95_ms_worst_replica"),
                    **{k: counts.get(k, 0) for k in HOST_COUNTS},
                }
            )
        flat: dict[str, Any] = {k: traffic.get(k) for k in TRAFFIC_METRICS}
        flat["cost"] = round(sum(float(p["cost"] or 0) for p in packages), 6)
        latencies = [
            float(p["latency_p95_ms"]) for p in packages if p["latency_p95_ms"] is not None
        ]
        flat["latency_p95_ms"] = max(latencies) if latencies else None
        for key in HOST_COUNTS:
            flat[key] = sum(int(p[key]) for p in packages)
        return {
            "window_s": traffic.get("window_s"),
            "metrics": flat,
            "by_package": {"traffic": traffic.get("by_package") or {}, "hosts": packages},
        }

    def traces(self, request_id: str | None, minutes: int, limit: int) -> dict[str, Any]:
        end = datetime.now(UTC)
        params = {
            "query.service_name": self.service,
            "query.start_time_min": (end - timedelta(minutes=minutes)).isoformat(),
            "query.start_time_max": end.isoformat(),
            "query.search_depth": str(max(limit, 20)),
        }
        found = self.pilot.request(
            "GET", self.jaeger_url, "/api/v3/traces", params=params, missing_ok=True
        )
        spans: list[dict[str, Any]] = []
        for resource in ((found or {}).get("result") or {}).get("resourceSpans") or []:
            for scope in resource.get("scopeSpans") or []:
                for span in scope.get("spans") or []:
                    kept = {
                        a["key"]: next(iter((a.get("value") or {}).values()), None)
                        for a in span.get("attributes") or []
                        if a.get("key") in SPAN_ATTRIBUTES
                    }
                    if request_id and kept.get("request_id") != request_id:
                        continue
                    start, stop = (
                        int(span.get("startTimeUnixNano", 0)),
                        int(span.get("endTimeUnixNano", 0)),
                    )
                    spans.append(
                        {
                            "trace_id": span.get("traceId"),
                            "name": span.get("name"),
                            "duration_ms": round((stop - start) / 1e6, 3),
                            "status": (span.get("status") or {}).get("code", "unset"),
                            **{k: kept.get(k) for k in SPAN_ATTRIBUTES if k in kept},
                        }
                    )
        return {"service": self.service, "spans": spans[:limit]}


class Monitors:
    def __init__(self, records: Records, metrics: Callable[[], dict[str, Any]]) -> None:
        self.records, self.metrics = records, metrics
        self.lock = threading.Lock()

    def configure(self, call: Call, args: dict[str, Any]) -> dict[str, Any]:
        op = str(args.get("operator") or "")
        if op not in OPERATORS:
            raise ToolFailure("invalid arguments: operator must be <, <=, > or >=")
        metric = str(args.get("metric") or "")
        try:
            threshold = float(args["threshold"])
            window = int(args["window_s"])
        except (KeyError, TypeError, ValueError):
            raise ToolFailure("invalid arguments: threshold and window_s") from None
        known = TRAFFIC_METRICS + HOST_COUNTS + ("cost", "latency_p95_ms")
        if metric not in known:
            raise ToolFailure(f"invalid arguments: metric must be one of {', '.join(known)}")
        with self.lock:
            existing = [r for r in self.records.read("monitors") if r["kind"] == "monitor"]
            monitor_id = f"MON-{len(existing) + 1}"
            self.records.add(
                "monitors",
                kind="monitor",
                monitor_id=monitor_id,
                usecase_id=call.claims.usecase_id,
                run_id=call.claims.run_id,
                metric=metric,
                operator=op,
                threshold=threshold,
                window_s=window,
            )
        return {"monitor_id": monitor_id}

    def evaluate(self) -> None:
        """Record a fired event when a monitor starts breaching, recovered when it stops."""
        with self.lock:
            rows = self.records.read("monitors")
            monitors = [r for r in rows if r["kind"] == "monitor"]
            if not monitors:
                return
            try:
                values = self.metrics()["metrics"]
            except ToolFailure:
                return
            for monitor in monitors:
                value = values.get(monitor["metric"])
                if value is None:
                    continue
                breach = OPERATORS[monitor["operator"]](float(value), float(monitor["threshold"]))
                events = [
                    r
                    for r in rows
                    if r.get("monitor_id") == monitor["monitor_id"]
                    and r["kind"] in ("fired", "recovered")
                ]
                firing = bool(events) and events[-1]["kind"] == "fired"
                if breach != firing:
                    self.records.add(
                        "monitors",
                        kind="fired" if breach else "recovered",
                        monitor_id=monitor["monitor_id"],
                        usecase_id=monitor["usecase_id"],
                        value=value,
                    )

    def read(self, usecase_id: str) -> dict[str, Any]:
        self.evaluate()
        rows = [r for r in self.records.read("monitors") if r["usecase_id"] == usecase_id]
        out = []
        for monitor in (r for r in rows if r["kind"] == "monitor"):
            events = [
                {"kind": r["kind"], "value": r["value"], "at": r["at"]}
                for r in rows
                if r.get("monitor_id") == monitor["monitor_id"] and r["kind"] != "monitor"
            ]
            out.append(
                {
                    **{
                        k: monitor[k]
                        for k in ("monitor_id", "metric", "operator", "threshold", "window_s")
                    },
                    "firing": bool(events) and events[-1]["kind"] == "fired",
                    "events": events,
                }
            )
        return {"monitors": out}

    def loop(self, interval_s: float) -> Callable[[], Coroutine[Any, Any, None]]:
        async def run() -> None:
            while True:
                await anyio.sleep(interval_s)
                await anyio.to_thread.run_sync(self.evaluate)

        return run


def handlers(pilot: Pilot, telemetry: Telemetry, monitors: Monitors) -> dict[str, Handler]:
    def observability_metrics(call: Call, args: dict[str, Any]) -> Any:
        return telemetry.metrics()

    def observability_traces(call: Call, args: dict[str, Any]) -> Any:
        return telemetry.traces(
            args.get("request_id"), int(args.get("minutes") or 15), int(args.get("limit") or 20)
        )

    def monitoring_configure(call: Call, args: dict[str, Any]) -> Any:
        return monitors.configure(call, args)

    def monitoring_read(call: Call, args: dict[str, Any]) -> Any:
        return monitors.read(call.claims.usecase_id)

    def feedback_read(call: Call, args: dict[str, Any]) -> Any:
        limit = int(args.get("limit") or 20)
        return pilot.request("GET", pilot.urls.traffic, "/feedback", params={"limit": limit})

    return {
        "observability_metrics": observability_metrics,
        "observability_traces": observability_traces,
        "monitoring_configure": monitoring_configure,
        "monitoring_read": monitoring_read,
        "feedback_read": feedback_read,
    }
