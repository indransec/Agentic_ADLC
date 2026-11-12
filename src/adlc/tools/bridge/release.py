"""``cd``, ``traffic_manager`` and ``kill_switch`` (feature 010 US4; FR-017, FR-018; research
R-10). They wrap prod-sim's own operations (feature 009): no Docker SDK, no Traefik.

- ``cd_deploy`` deploys only the hash authorised at T6 (bound by the platform, checked again
  here), as the candidate.
- ``traffic_manager_set``: shadow and canary route to the candidate as prod-sim does; ``full``
  promotes the deployed candidate to stable (prod-sim's ``full`` sends everything to stable),
  recording the previous stable so a rollback can restore it.
- ``traffic_manager_rollback``: all traffic to stable; after a promotion, the previous stable is
  redeployed.
- ``kill_switch_invoke``: stops prod-sim answering; only a person releases it (``pilot-kill``).
"""

from typing import Any

from adlc.tools.bridge.pilot import Pilot
from adlc.tools.bridge.records import Records
from adlc.tools.mcp_app import Call, Handler, ToolFailure

MODES = ("shadow", "canary", "full")


def handlers(pilot: Pilot, records: Records) -> dict[str, Handler]:
    prodsim = pilot.urls.prodsim

    def split() -> dict[str, Any]:
        found: dict[str, Any] = pilot.request("GET", prodsim, "/split")
        return {k: found.get(k) for k in ("stable", "candidate", "mode", "share")}

    def cd_deploy(call: Call, args: dict[str, Any]) -> Any:
        package = call.bound("authorised_hash")
        pilot.request(
            "POST",
            prodsim,
            "/deployments",
            json={"package_hash": package, "role": "candidate"},
            timeout_s=110,
        )
        return {"role": "candidate", "package_hash": package, "split": split()}

    def cd_status(call: Call, args: dict[str, Any]) -> Any:
        return split()

    def traffic_manager_set(call: Call, args: dict[str, Any]) -> Any:
        mode = str(args.get("mode") or "")
        if mode not in MODES:
            raise ToolFailure("invalid arguments: mode must be shadow, canary or full")
        now = split()
        if now["candidate"] is None:
            raise ToolFailure("refused: no candidate is deployed in prod-sim")
        if mode == "full":
            records.add(
                "promotions",
                usecase_id=call.claims.usecase_id,
                run_id=call.claims.run_id,
                previous_stable=now["stable"],
                promoted=now["candidate"],
            )
            pilot.request(
                "POST",
                prodsim,
                "/deployments",
                json={"package_hash": now["candidate"], "role": "stable"},
                timeout_s=110,
            )
            body: dict[str, Any] = {"mode": "full"}
        else:
            body = {"mode": mode}
            if mode == "canary" and args.get("share") is not None:
                body["share"] = float(args["share"])
        pilot.request("PUT", prodsim, "/split", json=body)
        return {"package_hash": now["candidate"], **split()}

    def traffic_manager_rollback(call: Call, args: dict[str, Any]) -> Any:
        now = split()
        promotions = [r for r in records.read("promotions") if r.get("promoted") == now["stable"]]
        restored = None
        if promotions and promotions[-1].get("previous_stable"):
            restored = promotions[-1]["previous_stable"]
            pilot.request(
                "POST",
                prodsim,
                "/deployments",
                json={"package_hash": restored, "role": "stable"},
                timeout_s=110,
            )
        pilot.request("PUT", prodsim, "/split", json={"mode": "full"})
        return {"restored_stable": restored, **split()}

    def kill_switch_invoke(call: Call, args: dict[str, Any]) -> Any:
        reason = str(args.get("reason") or "")[:500]
        if not reason:
            raise ToolFailure("invalid arguments: reason")
        answer = pilot.request(
            "POST", prodsim, "/kill", json={"action": "activate", "reason": reason}
        )
        return {"active": bool(answer.get("active")), "released_by": "a person (pilot-kill)"}

    return {
        "cd_deploy": cd_deploy,
        "cd_status": cd_status,
        "traffic_manager_set": traffic_manager_set,
        "traffic_manager_rollback": traffic_manager_rollback,
        "kill_switch_invoke": kill_switch_invoke,
    }
