"""Evidence from the pilot through the bridge (feature 010, research R-12, FR-009).

012: ``telemetry`` comes from the pilot's observability and monitors, read with a service token
naming the use case; which pilot metric feeds which field is spec content (the evidence-sources
catalogue's ``from_pilot``), so no metric name is in code.

``env.dev``, ``env.test`` and ``env.prod`` and ``template.version`` come from the pilot's own
operations when the bridge answers, so prerequisites (dev provisioned, template pinned) and
controls (deployed hash) read real evidence. The platform reads with a service token
(``run_id: platform``, read scopes only). When the bridge is not configured or does not answer,
this provider answers "not available" and the composite provider falls back to synthetic
evidence, labelled synthetic.
"""

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Answer, Evidence
from adlc.policy.values import NOT_AVAILABLE
from adlc.tools.client import McpClient, ToolUnavailable
from adlc.tools.token import issue, sign

HOST = "bridge"
SERVICE_RUN = "platform"
SERVICE_SCOPES = (
    "mcp:pilot_env:read",
    "mcp:cd:read",
    "mcp:observability:read",
    "mcp:monitoring:read",
)
SOURCES = ("env", "template", "telemetry")
Catalogue = Callable[[str], Mapping[str, Any] | None]


class PilotRefused(Exception):
    """The bridge answered, with a tool error (e.g. a pilot host did not answer it)."""


class PilotEvidence:
    def __init__(
        self, client: McpClient, key: str, *, now: Callable[[], float] = time.time
    ) -> None:
        self.client, self.key, self.now = client, key, now
        self.catalogue: Catalogue | None = None  # set by the policy factory (012)

    def _call(
        self, server: str, tool: str, arguments: dict[str, Any], usecase_id: str = SERVICE_RUN
    ) -> Any:
        token = sign(
            issue(
                run_id=SERVICE_RUN,
                usecase_id=usecase_id,
                terminal_id=SERVICE_RUN,
                attempt=1,
                scopes=SERVICE_SCOPES,
                now=self.now(),
            ),
            self.key,
        )
        failed, text = self.client(HOST, server, tool, arguments, token)
        if failed:
            raise PilotRefused(text)
        return json.loads(text)

    def _environment(self, name: str, versions: dict[str, str]) -> dict[str, Any]:
        try:
            status = self._call("pilot_env", "status", {"environment": name})
        except PilotRefused:  # the bridge answered; the host did not: fail closed (010 T043)
            return {"provisioned": False, "running": False, "healthy": False, "deployed_hash": None}
        running = bool(status.get("running"))
        replicas = status.get("replicas") or []
        return {
            "provisioned": True,  # the host answered and its definition loads
            "running": running,
            "healthy": running and all(bool(r.get("healthy")) for r in replicas),
            "deployed_hash": status.get("package_hash") if running else None,
            "infra_version": versions.get(name),
        }

    def _prod(self) -> str | None:
        """Prod-sim's deployed hash: the stable package (a full rollout promotes the candidate to
        stable); ``None`` when prod-sim cannot be read (``env.prod`` is then not available)."""
        try:
            split = self._call("cd", "status", {})
        except (ToolUnavailable, PilotRefused, ValueError):
            return None
        stable = split.get("stable")
        return str(stable) if stable else None

    def _mapping(self, source: str) -> Mapping[str, Any]:
        found = self.catalogue("evidence_sources") if self.catalogue else None
        for entry in (found or {}).get("evidence_sources") or []:
            if entry.get("id") == source and isinstance(entry.get("from_pilot"), Mapping):
                return dict(entry["from_pilot"])
        return {}

    def _telemetry(self, usecase_id: str) -> Answer:
        mapping = self._mapping("telemetry")
        if not mapping:
            return NOT_AVAILABLE
        try:
            metrics = self._call("observability", "metrics", {}, usecase_id).get("metrics") or {}
            monitors = self._call("monitoring", "read", {}, usecase_id).get("monitors") or []
        except PilotRefused:
            return NOT_AVAILABLE
        found: dict[str, Any] = {}
        for field, how in mapping.items():
            value = _measure(metrics, how)
            if value is not None:
                found[field] = value
        found["monitors"] = {
            str(m.get("metric")): _number(metrics.get(m.get("metric"))) is not None
            for m in monitors
        }
        return Evidence(found, "pilot")

    def get(self, source: str, context: EvalContext) -> Answer:
        if source not in SOURCES:
            return NOT_AVAILABLE
        if source == "telemetry":
            if context.usecase_id is None:
                return NOT_AVAILABLE
            try:
                return self._telemetry(context.usecase_id)
            except (ToolUnavailable, ValueError, AttributeError):
                return NOT_AVAILABLE
        try:
            try:
                infra = self._call("pilot_env", "infra", {})
            except PilotRefused:
                infra = None
            if source == "template":
                if infra is None:  # never guess a pinned version
                    return NOT_AVAILABLE
                version = f"{infra.get('template_id')}@{infra.get('template_version')}"
                return Evidence({"version": version, "id": infra.get("template_id")}, "pilot")
            versions = {
                str(d.get("environment")): str(d.get("version"))
                for d in (infra or {}).get("definitions") or []
            }
            found: dict[str, Any] = {
                "dev": self._environment("dev", versions),
                "test": self._environment("test", versions),
            }
            prod = self._prod()
            if prod is not None:
                found["prod"] = {"deployed_hash": prod, "infra_version": versions.get("prod-sim")}
            return Evidence(found, "pilot")
        except (ToolUnavailable, ValueError, AttributeError):
            return NOT_AVAILABLE


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _measure(metrics: Mapping[str, Any], how: Any) -> float | int | None:
    """One telemetry field from the pilot's metrics: a metric, or a ratio (``None`` when the
    pilot did not measure it, or the denominator is zero)."""
    if not isinstance(how, Mapping):
        return None
    if "metric" in how:
        value = metrics.get(str(how["metric"]))
        return value if _number(value) is not None else None
    numerator, denominator = (_number(metrics.get(str(n))) for n in how.get("ratio") or ("", ""))
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator * float(how.get("scale") or 1), 6)
