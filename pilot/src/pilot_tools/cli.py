"""Operator commands on the pilot network (contracts/pilot-api.md): ``pilot-env``,
``pilot-split``, ``pilot-fault`` and ``pilot-traffic-ctl``. Hosts are addressed by service name;
``PILOT_HOST_PORT`` and ``PILOT_TRAFFIC_URL`` override the defaults."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

import httpx

PRODSIM = "pilot-prodsim"


def host_url(name: str) -> str:
    if name.startswith("http"):
        return name.rstrip("/")
    return f"http://{name}:{os.environ.get('PILOT_HOST_PORT', '8100')}"


def traffic_url() -> str:
    return os.environ.get("PILOT_TRAFFIC_URL", "http://pilot-traffic:8200").rstrip("/")


def _show(reply: httpx.Response) -> int:
    try:
        body: Any = reply.json()
    except ValueError:
        body = reply.text
    print(json.dumps(body, indent=1) if body not in ("", None) else reply.status_code)
    return 0 if reply.status_code < 400 else 1


def _settings(pairs: Sequence[str]) -> dict[str, str]:
    found = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise SystemExit(f"--set needs key=value, not {pair!r}")
        found[key] = value
    return found


def env_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pilot-env", description="Environment operations")
    parser.add_argument("host")
    parser.add_argument("action", choices=["create", "status", "delete", "infra"])
    parser.add_argument("--package")
    parser.add_argument("--set", action="append", default=[])
    args = parser.parse_args(argv)
    base = host_url(args.host)
    if args.action == "create":
        if not args.package:
            raise SystemExit("create needs --package")
        body = {"package_hash": args.package, "settings": _settings(args.set)}
        reply = httpx.post(f"{base}/environment", json=body, timeout=60)
    elif args.action == "status":
        reply = httpx.get(f"{base}/environment", timeout=10)
    elif args.action == "infra":
        reply = httpx.get(f"{base}/infra", timeout=10)
    else:
        reply = httpx.delete(f"{base}/environment", timeout=60)
    sys.exit(_show(reply))


def split_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pilot-split", description="Prod-sim deployments and split"
    )
    parser.add_argument("mode", choices=["shadow", "canary", "full", "deploy", "status"])
    parser.add_argument("--share", type=float)
    parser.add_argument("--stable")
    parser.add_argument("--candidate")
    parser.add_argument("--host", default=PRODSIM)
    args = parser.parse_args(argv)
    base = host_url(args.host)
    if args.mode == "status":
        sys.exit(_show(httpx.get(f"{base}/split", timeout=10)))
    for role in ("stable", "candidate"):
        package = getattr(args, role)
        if package:
            deployed = httpx.post(
                f"{base}/deployments", json={"package_hash": package, "role": role}, timeout=60
            )
            if _show(deployed):
                sys.exit(1)
    if args.mode == "deploy":
        sys.exit(0)
    body: dict[str, Any] = {"mode": args.mode}
    if args.share is not None:
        body["share"] = args.share
    sys.exit(_show(httpx.put(f"{base}/split", json=body, timeout=10)))


def fault_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pilot-fault", description="Demo faults in prod-sim")
    parser.add_argument("fault", choices=["model_swap", "pii_leak", "status"])
    parser.add_argument("action", nargs="?", choices=["trigger", "revert"])
    parser.add_argument("--share", type=float)
    parser.add_argument("--host", default=PRODSIM)
    args = parser.parse_args(argv)
    base = host_url(args.host)
    if args.fault == "status":
        sys.exit(_show(httpx.get(f"{base}/faults", timeout=10)))
    if args.action is None:
        raise SystemExit("give trigger or revert")
    body: dict[str, Any] = {"action": args.action}
    if args.share is not None:
        body["parameters"] = {"share": args.share}
    sys.exit(_show(httpx.post(f"{base}/faults/{args.fault}", json=body, timeout=30)))


def traffic_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pilot-traffic-ctl", description="Traffic generator")
    parser.add_argument("action", choices=["rate", "start", "pause", "metrics"])
    parser.add_argument("value", nargs="?", type=float)
    args = parser.parse_args(argv)
    base = traffic_url()
    if args.action == "rate":
        if args.value is None:
            raise SystemExit("rate needs a number of incidents per second")
        reply = httpx.put(f"{base}/rate", json={"per_second": args.value}, timeout=10)
    elif args.action == "metrics":
        reply = httpx.get(f"{base}/metrics", timeout=10)
    else:
        reply = httpx.post(f"{base}/{args.action}", timeout=10)
    sys.exit(_show(reply))
