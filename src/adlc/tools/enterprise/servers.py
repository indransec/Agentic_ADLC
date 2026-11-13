"""The enterprise mocks (feature 010 US6, FR-022): ITSM (``servicenow``), ``cmdb``,
``agent_registry``, ``iam``, ``grc``, ``control_library`` and the ``eval_store``. They implement
the tool names and shapes the real systems' servers would, keep their records in the platform and
scope every record to the run token's use case."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from adlc.tools.enterprise.records import EnterpriseStore
from adlc.tools.mcp_app import Call, Handler, ToolFailure

# 012: autonomy level (registry entry at deployment) and dependants (retirement checks)
AGENT_ATTRIBUTES = (
    "name",
    "version",
    "package_hash",
    "owner",
    "status",
    "autonomy_level",
    "depends_on",
)
WINDOW = timedelta(days=7)
MAX_ATTRIBUTE = 2000


def _attributes(args: dict[str, Any], allowed: tuple[str, ...] | None = None) -> dict[str, str]:
    raw = args.get("attributes")
    if not isinstance(raw, dict) or not raw or len(raw) > 50:
        raise ToolFailure("invalid arguments: attributes must be an object of 1 to 50 values")
    if allowed is not None and set(raw) - set(allowed):
        raise ToolFailure(f"invalid arguments: attributes are {', '.join(allowed)}")
    return {str(k)[:100]: str(v)[:MAX_ATTRIBUTE] for k, v in raw.items()}


def _when(value: Any, name: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        raise ToolFailure(f"invalid arguments: {name} must be an ISO date-time") from None


def handlers(store: EnterpriseStore, controls_file: Path) -> dict[str, Handler]:
    controls = YAML(typ="safe").load(controls_file.read_text())["controls"]

    def uc(call: Call) -> str:
        return call.claims.usecase_id

    # ------------------------------------------------------------ eval store
    def eval_store_read(call: Call, args: dict[str, Any]) -> Any:
        kind = args.get("kind")
        return {
            "results": store.evidence(uc(call), kind),
            "notes": store.records("eval_store", uc(call), "note"),
        }

    def eval_store_write(call: Call, args: dict[str, Any]) -> Any:
        body = {
            "note": str(args.get("note") or "")[:10_000],
            "result_id": args.get("result_id"),
            "author": "agent",
        }
        if not body["note"]:
            raise ToolFailure("invalid arguments: note")
        made = store.add("eval_store", "note", "NOTE", call.claims, body)
        return {"note_id": made["id"]}

    # ------------------------------------------------------------ ITSM
    def change_create(call: Call, args: dict[str, Any]) -> Any:
        # 012: the window opens now unless the caller names one (research R-10)
        start = (
            _when(args["window_start"], "window_start")
            if args.get("window_start")
            else datetime.now(UTC)
        )
        end = _when(args["window_end"], "window_end") if args.get("window_end") else start + WINDOW
        if end <= start:
            raise ToolFailure("invalid arguments: window_end must be after window_start")
        body = {
            "summary": str(args.get("summary") or "")[:500],
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "risk": str(args.get("risk") or ""),
            "plan": str(args.get("plan") or "")[:10_000],
            "state": "new",
        }
        made = store.add("servicenow", "change", "CHG", call.claims, body)
        return {"change_id": made["id"], "state": "new"}

    def incident_create(call: Call, args: dict[str, Any]) -> Any:
        body = {
            "summary": str(args.get("summary") or "")[:500],
            "severity": int(args.get("severity") or 4),
            "description": str(args.get("description") or "")[:10_000],
            "state": "new",
        }
        made = store.add("servicenow", "incident", "INC", call.claims, body)
        return {"incident_id": made["id"], "state": "new"}

    def servicenow_read(call: Call, args: dict[str, Any]) -> Any:
        kind = str(args.get("kind") or "")
        if kind not in ("change", "incident"):
            raise ToolFailure("invalid arguments: kind must be change or incident")
        return {"records": store.records("servicenow", uc(call), kind, args.get("id"))}

    # ------------------------------------------------------------ CMDB and agent registry
    def write(
        system: str, kind: str, prefix: str, key: str, allowed: tuple[str, ...] | None
    ) -> Handler:
        def handler(call: Call, args: dict[str, Any]) -> Any:
            attributes = _attributes(args, allowed)
            existing = args.get(key)
            if existing:
                made = store.update(system, str(existing), call.claims, attributes)
            else:
                made = store.add(system, kind, prefix, call.claims, attributes)
            return {key: made["id"], "version": made["record_version"]}

        return handler

    def read(system: str, key: str) -> Handler:
        def handler(call: Call, args: dict[str, Any]) -> Any:
            return {"records": store.records(system, uc(call), record_id=args.get(key))}

        return handler

    # ------------------------------------------------------------ IAM
    def iam_read(call: Call, args: dict[str, Any]) -> Any:
        agents = store.records("agent_registry", uc(call))
        revocations = store.records("iam", uc(call), "revocation")
        revoked = {r["what"] for r in revocations}
        return {
            "identities": [
                {
                    "identity": f"agent:{a['id']}",
                    "agent": a.get("name"),
                    "identity_revoked": "identity" in revoked,
                    "tool_scopes_revoked": "tool_scopes" in revoked,
                }
                for a in agents
            ],
            "revocations": revocations,
        }

    def iam_revoke(call: Call, args: dict[str, Any]) -> Any:
        what = str(args.get("what") or "")
        if what not in ("identity", "tool_scopes"):
            raise ToolFailure("invalid arguments: what must be identity or tool_scopes")
        agents = [f"agent:{a['id']}" for a in store.records("agent_registry", uc(call))]
        body = {"what": what, "reason": str(args.get("reason") or "")[:500], "identities": agents}
        made = store.add("iam", "revocation", "REV", call.claims, body)
        return {"revocation_id": made["id"], "identities": agents}

    # ------------------------------------------------------------ GRC and controls
    def grc_write(call: Call, args: dict[str, Any]) -> Any:
        body = {
            "title": str(args.get("title") or "")[:200],
            "report": str(args.get("report") or "")[:50_000],
        }
        if not body["title"] or not body["report"]:
            raise ToolFailure("invalid arguments: title and report")
        return {"report_id": store.add("grc", "report", "GRC", call.claims, body)["id"]}

    def control_library_read(call: Call, args: dict[str, Any]) -> Any:
        wanted, topic = args.get("control_id"), args.get("topic")
        found = [
            c
            for c in controls
            if (not wanted or c["id"] == wanted) and (not topic or c["topic"] == topic)
        ]
        if wanted and not found:
            raise ToolFailure(f"not found: control {wanted}")
        return {"controls": found}

    return {
        "eval_store_read": eval_store_read,
        "eval_store_write": eval_store_write,
        "servicenow_change_create": change_create,
        "servicenow_incident_create": incident_create,
        "servicenow_read": servicenow_read,
        "cmdb_read": read("cmdb", "ci_id"),
        "cmdb_write": write("cmdb", "ci", "CI", "ci_id", None),
        "agent_registry_read": read("agent_registry", "agent_id"),
        "agent_registry_write": write(
            "agent_registry", "agent", "AG", "agent_id", AGENT_ATTRIBUTES
        ),
        "iam_read": iam_read,
        "iam_revoke": iam_revoke,
        "grc_write": grc_write,
        "grc_read": read("grc", "report_id"),
        "control_library_read": control_library_read,
    }
