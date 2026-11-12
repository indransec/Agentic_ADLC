"""``pilot_env``: the pilot's dev and test environments and the template's infrastructure
definitions (feature 010 US1, FR-008; research R-03).

The environment is the one bound to the call (the environment scope the terminal's spec grants),
never chosen by the model. In test the package is the use case's candidate, also bound; in dev the
building terminal names the hash it
built.
"""

import re
from typing import Any

from adlc.tools.bridge.pilot import Pilot
from adlc.tools.mcp_app import Call, Handler, ToolFailure

HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
ENVIRONMENTS = ("dev", "test")
INFRA_ENVIRONMENTS = ("dev", "test", "prod-sim")


def _settings(args: dict[str, Any]) -> dict[str, str]:
    raw = args.get("settings") or {}
    if not isinstance(raw, dict) or len(raw) > 20:
        raise ToolFailure("invalid arguments: settings must be an object of at most 20 values")
    return {str(k): str(v) for k, v in raw.items()}


def handlers(pilot: Pilot) -> dict[str, Handler]:
    def create(call: Call, args: dict[str, Any]) -> Any:
        environment = call.bound("environment")
        if environment == "test":
            package = call.bound("candidate_hash")
        else:
            package = str(args.get("package_hash") or "")
            if not HASH.match(package):
                raise ToolFailure("invalid arguments: package_hash (sha256:<64 hex>) is required")
        body = {"package_hash": package, "settings": _settings(args)}
        answer = pilot.request(
            "POST", pilot.urls.host(environment), "/environment", json=body, timeout_s=110
        )
        return {
            "environment": environment,
            "package_hash": answer.get("package_hash"),
            "replicas": answer.get("replicas"),
            "settings": answer.get("settings"),
        }

    def status(call: Call, args: dict[str, Any]) -> Any:
        environment = str(args.get("environment") or "")
        if environment not in ENVIRONMENTS:
            raise ToolFailure("invalid arguments: environment must be dev or test")
        answer = pilot.request("GET", pilot.urls.host(environment), "/environment", missing_ok=True)
        if answer is None:
            return {"environment": environment, "running": False}
        return {"running": True, **answer}

    def delete(call: Call, args: dict[str, Any]) -> Any:
        environment = call.bound("environment")
        pilot.request("DELETE", pilot.urls.host(environment), "/environment", timeout_s=55)
        return {"environment": environment, "deleted": True}

    def infra(call: Call, args: dict[str, Any]) -> Any:
        wanted = args.get("environment")
        if wanted is not None and wanted not in INFRA_ENVIRONMENTS:
            raise ToolFailure("invalid arguments: environment must be dev, test or prod-sim")
        return definitions(pilot, wanted)

    return {
        "pilot_env_create": create,
        "pilot_env_status": status,
        "pilot_env_delete": delete,
        "pilot_env_infra": infra,
    }


def definitions(pilot: Pilot, environment: str | None = None) -> dict[str, Any]:
    """The template's infrastructure definitions, as the dev host reads them from the template."""
    answer = pilot.request("GET", pilot.urls.dev, "/infra")
    found = [
        d
        for d in answer.get("definitions") or []
        if environment is None or d.get("environment") == environment
    ]
    return {
        "template_id": answer.get("template_id"),
        "template_version": answer.get("template_version"),
        "definitions": found,
    }
