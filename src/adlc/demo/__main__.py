"""``adlc-demo`` (feature 014, contracts/cli.md): run the demo script on the platform.

It runs its own orchestrator worker (stop the stack's first; ``make demo`` does) with rehearsed
agent replies (``--live``: the configured model profile), acts as the people in the account file
in ``--auto``, and otherwise tells the presenter what to do in the web app and waits. A pilot
fault is asked of the host wrapper on stdout (``fault <name> <action>``); the wrapper answers
``done`` on stdin. Exit 0 when every step met its expectation.
"""

import importlib
import json
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import typer

from adlc.agents.replay import (
    AgentReplies,
    Replayer,
    load_references,
    read_recording,
    replay_gateway,
)
from adlc.agents.replay_cli import build_stack
from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import OrchestratorSettings
from adlc.demo.driver import DemoDriver
from adlc.demo.script import load_script
from adlc.identity.catalogue import load_role_ids
from adlc.inbox.changes import ChangeService
from adlc.orchestration.monitors import MonitorEvaluator

app = typer.Typer(help="Run the end-to-end demo script (feature 014).")
POLL_S = 1.0


class StdIo:
    def __init__(self, poll_s: float) -> None:
        self.poll_s = poll_s

    def say(self, text: str) -> None:
        print(text, flush=True)

    def fault(self, name: str, action: str) -> None:
        print(f"fault {name} {action}", flush=True)
        answer = sys.stdin.readline().strip()
        if answer != "done":
            raise RuntimeError(f"the wrapper did not apply fault {name} {action}: {answer!r}")

    def pause(self) -> None:
        time.sleep(self.poll_s)


def rehearsed(spec: str, root: Path) -> dict[str, list[Any]]:
    """``<module>:<function>`` from the demo assets (importable from the script's folder)."""
    module, _, function = spec.partition(":")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    found: dict[str, list[Any]] = getattr(importlib.import_module(module), function)()
    return found


@app.command()
def main(
    script: Annotated[Path, typer.Option(help="The demo script")] = Path("demo/script.yaml"),
    auto: Annotated[bool, typer.Option(help="Take the human steps too")] = False,
    live: Annotated[bool, typer.Option(help="Call the configured models")] = False,
    from_step: Annotated[int, typer.Option(help="Resume from this step")] = 1,
    profile: Annotated[str | None, typer.Option(help="Model profile with --live")] = None,
    references: Annotated[Path, typer.Option()] = Path("data/reference_usecases"),
    out: Annotated[Path, typer.Option(help="Report folder")] = Path("demo-report"),
) -> None:
    settings = load_settings_or_exit(OrchestratorSettings)
    loaded = load_script(script, load_role_ids(settings.role_catalogue))
    root = script.resolve().parent.parent
    stack = build_stack(settings, profile, live, "adlc-demo")
    if not live:
        replies = {
            **read_recording(root / loaded.recordings),
            **rehearsed(loaded.rehearsed, root),
        }
        stack.switch.current = replay_gateway(
            stack.models, AgentReplies(stack.prompts, replies), stack.recorder
        )
    orchestrator = stack.orchestrator
    replayer = Replayer(orchestrator.service, orchestrator.runs, orchestrator.drain, stack.people)
    driver = DemoDriver(
        loaded,
        {r.id: r for r in load_references(references)},
        replayer,
        ChangeService(stack.engine, stack.registry, orchestrator.service, stack.clock),
        MonitorEvaluator(
            stack.engine,
            stack.registry,
            stack.policy,
            orchestrator.service,
            settings.monitor_interval,
        ),
        StdIo(POLL_S),
        auto=auto,
    )
    report = driver.run(from_step)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report.markdown())
    (out / "report.json").write_text(json.dumps(report.to_json(), indent=1, default=str))
    print(report.markdown(), flush=True)
    if not report.ok:
        failed = next(s for s in report.steps if s.outcome != "ok")
        if live:  # analysis A4: a live model outage or misstep; rehearsed replies always run
            print(
                f"The live run stopped at step {failed.number}. To continue with rehearsed "
                f"replies: make demo FROM_STEP={failed.number}",
                flush=True,
            )
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
