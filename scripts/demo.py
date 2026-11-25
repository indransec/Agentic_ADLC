"""The host side of the demo (feature 014, research R-03; ``make demo``, ``make demo-local``).

The driver (``adlc-demo``) runs its own orchestrator worker, so the stack's worker must not run.
It asks this wrapper for pilot faults on stdout (``fault <name> <action>``), which are applied
with the pilot's operator tool (the platform never reaches the pilot's faults).

- **Compose** (default): stops the stack's orchestrator, runs the driver in the orchestrator
  image with the demo assets mounted, applies faults with ``pilot-fault`` in the ``pilot-tools``
  container, and starts the orchestrator again at the end.
- **Local** (``--local``, ``make demo-local``): the platform runs without Docker, started by
  ``make local-no-worker`` (every process of ``deploy/Procfile.local`` except the orchestrator).
  The driver runs on the host with the settings of ``.env`` and ``deploy/local.env``; the pilot's
  operator tools run from ``pilot/`` against the local pilot ports.

    uv run python -m scripts.demo [--local] [--auto] [--live] [--from-step N]
"""

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

COMPOSE = ["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env"]
HEARTBEAT_WAIT_S = 45  # the replay refuses while the stopped worker's heartbeat is recent
FAULT_ACTIONS = {"trigger", "revert"}
TRAFFIC_RATE = 5  # requests per second during the demo
REPORTS = Path("demo-report")  # git-ignored; the driver output of each run
# deploy/local.env gives these; the defaults are the same local ports
LOCAL_PRODSIM = ("ADLC_BRIDGE_PILOT_PRODSIM_URL", "http://127.0.0.1:8103")
LOCAL_TRAFFIC = ("ADLC_BRIDGE_PILOT_TRAFFIC_URL", "http://127.0.0.1:8200")


class Compose:
    """The stack in Docker Compose."""

    def pilot_tool(self, args: Sequence[str], check: bool = True) -> None:
        subprocess.run([*COMPOSE, "run", "--rm", "-T", "pilot-tools", *args], check=check)  # noqa: S603

    def fault_args(self, name: str, action: str) -> list[str]:
        return ["pilot-fault", name, action]

    def before(self, wait: bool) -> None:
        subprocess.run([*COMPOSE, "stop", "orchestrator"], check=True)
        if wait:
            print(
                f"demo: waiting {HEARTBEAT_WAIT_S} s for the stopped worker's heartbeat to age",
                flush=True,
            )
            time.sleep(HEARTBEAT_WAIT_S)

    def driver(self, args: list[str]) -> list[str]:
        mount = f"{Path('demo').resolve()}:/app/demo:ro"
        return [*COMPOSE, "run", "--rm", "-i", "-T", "-v", mount, "orchestrator", *args]

    def after(self) -> None:
        subprocess.run([*COMPOSE, "start", "orchestrator"], check=False)


class Local:
    """The stack without Docker (``make local-no-worker``)."""

    def __init__(self) -> None:
        # pilot/ is its own uv project: not this one's virtual environment
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env["PILOT_TRAFFIC_URL"] = os.environ.get(*LOCAL_TRAFFIC)
        self.pilot_env = env

    def pilot_tool(self, args: Sequence[str], check: bool = True) -> None:
        subprocess.run(  # noqa: S603
            ["uv", "run", "-q", "--project", "pilot", *args],  # noqa: S607
            check=check,
            env=self.pilot_env,
        )

    def fault_args(self, name: str, action: str) -> list[str]:
        return ["pilot-fault", name, action, "--host", os.environ.get(*LOCAL_PRODSIM)]

    def before(self, wait: bool) -> None:
        # The driver refuses while a worker's heartbeat is recent, with the reason.
        print("demo: local stack (make local-no-worker); the driver runs on the host", flush=True)

    def driver(self, args: list[str]) -> list[str]:
        return ["uv", "run", *args]

    def after(self) -> None:
        print(
            "demo: the platform's worker is not running; to go on without the driver, stop "
            "make local-no-worker and start make local",
            flush=True,
        )


def prepare_pilot(stack: Compose | Local) -> None:
    """014 rehearsal finding: the rollout and the drift need traffic, and a previous run may have
    left the model swapped. Operator actions on the pilot, as in deploy/README.md."""
    print("demo: preparing the pilot (model swap reverted, traffic at 5/s)", flush=True)
    stack.pilot_tool(stack.fault_args("model_swap", "revert"), check=False)  # "not active" is fine
    stack.pilot_tool(["pilot-traffic-ctl", "rate", str(TRAFFIC_RATE)])
    stack.pilot_tool(["pilot-traffic-ctl", "start"])


def fault(stack: Compose | Local, name: str, action: str) -> None:
    if action not in FAULT_ACTIONS or not name.replace("_", "").isalnum():
        raise SystemExit(f"demo: refusing an unexpected fault request: {name} {action}")
    stack.pilot_tool(stack.fault_args(name, action))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="the stack runs without Docker")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--from-step", type=int, default=1)
    parser.add_argument("--no-wait", action="store_true", help="skip the heartbeat wait")
    args = parser.parse_args(argv)
    stack: Compose | Local = Local() if args.local else Compose()
    prepare_pilot(stack)
    stack.before(wait=not args.no_wait)
    command = stack.driver(
        ["adlc-demo", "--script", "demo/script.yaml", "--from-step", str(args.from_step)]
    )
    if args.auto:
        command.append("--auto")
    if args.live:
        command.append("--live")
    driver = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)  # noqa: S603
    REPORTS.mkdir(exist_ok=True)
    log = (REPORTS / f"demo-{time.strftime('%Y%m%d-%H%M%S')}.log").open("w")
    if driver.stdin is None or driver.stdout is None:
        raise SystemExit("demo: the driver's pipes did not open")
    try:
        for line in driver.stdout:
            if line.startswith("fault "):
                _, name, action = line.split()
                print(f"demo: applying pilot fault {name} {action}", flush=True)
                fault(stack, name, action)
                driver.stdin.write("done\n")
                driver.stdin.flush()
                continue
            print(line, end="", flush=True)
            log.write(line)
        return driver.wait()
    finally:
        log.close()
        print(f"demo: the output is kept in {log.name}", flush=True)
        stack.after()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
