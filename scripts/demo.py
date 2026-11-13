"""The host side of the demo (feature 014, research R-03; ``make demo``).

Stops the stack's orchestrator (the driver runs its own worker), runs ``adlc-demo`` in the
orchestrator image with the demo assets mounted, relays its output, and applies the pilot faults
it asks for with the pilot's operator tool (``pilot-fault`` in the ``pilot-tools`` container: the
platform never reaches the pilot's faults). The stack's orchestrator is started again at the end.

    uv run python -m scripts.demo [--auto] [--live] [--from-step N]
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

COMPOSE = ["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env"]
HEARTBEAT_WAIT_S = 45  # the replay refuses while the stopped worker's heartbeat is recent
FAULT_ACTIONS = {"trigger", "revert"}
TRAFFIC_RATE = 5  # requests per second during the demo
REPORTS = Path("demo-report")  # git-ignored; the driver output of each run


def fault(name: str, action: str) -> None:
    if action not in FAULT_ACTIONS or not name.replace("_", "").isalnum():
        raise SystemExit(f"demo: refusing an unexpected fault request: {name} {action}")
    subprocess.run(
        [*COMPOSE, "run", "--rm", "-T", "pilot-tools", "pilot-fault", name, action], check=True
    )


def pilot_tool(*args: str, check: bool = True) -> None:
    subprocess.run([*COMPOSE, "run", "--rm", "-T", "pilot-tools", *args], check=check)  # noqa: S603


def prepare_pilot() -> None:
    """014 rehearsal finding: the rollout and the drift need traffic, and a previous run may have
    left the model swapped. Operator actions on the pilot, as in deploy/README.md."""
    print("demo: preparing the pilot (model swap reverted, traffic at 5/s)", flush=True)
    pilot_tool("pilot-fault", "model_swap", "revert", check=False)  # "not active" is fine
    pilot_tool("pilot-traffic-ctl", "rate", str(TRAFFIC_RATE))
    pilot_tool("pilot-traffic-ctl", "start")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--from-step", type=int, default=1)
    parser.add_argument("--no-wait", action="store_true", help="skip the heartbeat wait")
    args = parser.parse_args(argv)
    prepare_pilot()
    subprocess.run([*COMPOSE, "stop", "orchestrator"], check=True)
    if not args.no_wait:
        print(
            f"demo: waiting {HEARTBEAT_WAIT_S} s for the stopped worker's heartbeat to age",
            flush=True,
        )
        time.sleep(HEARTBEAT_WAIT_S)
    command = [
        *COMPOSE,
        "run",
        "--rm",
        "-i",
        "-T",
        "-v",
        f"{Path('demo').resolve()}:/app/demo:ro",
        "orchestrator",
        "adlc-demo",
        "--script",
        "demo/script.yaml",
        "--from-step",
        str(args.from_step),
    ]
    if args.auto:
        command.append("--auto")
    if args.live:
        command.append("--live")
    driver = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    REPORTS.mkdir(exist_ok=True)
    log = (REPORTS / f"demo-{time.strftime('%Y%m%d-%H%M%S')}.log").open("w")
    if driver.stdin is None or driver.stdout is None:
        raise SystemExit("demo: the driver's pipes did not open")
    try:
        for line in driver.stdout:
            if line.startswith("fault "):
                _, name, action = line.split()
                print(f"demo: applying pilot fault {name} {action}", flush=True)
                fault(name, action)
                driver.stdin.write("done\n")
                driver.stdin.flush()
                continue
            print(line, end="", flush=True)
            log.write(line)
        return driver.wait()
    finally:
        log.close()
        print(f"demo: the output is kept in {log.name}", flush=True)
        subprocess.run([*COMPOSE, "start", "orchestrator"], check=False)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
