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
from pydantic import ValidationError

from adlc.agents.replay import (
    AgentReplies,
    Replayer,
    load_references,
    read_recording,
    replay_gateway,
)
from adlc.agents.replay_cli import build_stack
from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import BoardSettings, OrchestratorSettings
from adlc.demo.board import BoardActor
from adlc.demo.driver import DemoDriver
from adlc.demo.script import load_script
from adlc.demo.tokens import TokensFileError, read_tokens
from adlc.engagement.ado import AdoBoard
from adlc.engagement.wiring import build
from adlc.identity.accounts import load_accounts
from adlc.identity.catalogue import load_role_ids
from adlc.inbox.changes import ChangeService
from adlc.orchestration.monitors import MonitorEvaluator
from adlc.orchestration.service import Actor

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


def on_the_board(
    settings: OrchestratorSettings, engine: Any, drain: Any
) -> tuple[BoardActor | None, Any]:
    """020: with the board sync on, the people act on the board with their own tokens (the file
    at ``ADLC_DEMO_BOARD_TOKENS``) and the CoE reconciles through the engagement layer."""
    try:
        board_settings = BoardSettings()  # type: ignore[call-arg]
    except ValidationError:
        return None, None
    if not board_settings.board_enabled or board_settings.board_token is None:
        return None, None
    if settings.demo_board_tokens is None:
        raise typer.BadParameter("ADLC_DEMO_BOARD_TOKENS is needed for the demo on the board")
    try:
        tokens = read_tokens(settings.demo_board_tokens)
    except TokensFileError as error:
        raise typer.BadParameter(str(error)) from None
    accounts = load_accounts(
        board_settings.accounts_file, load_role_ids(settings.role_catalogue), settings.env
    )

    def user_of(actor: Any) -> str:
        account = accounts.get(actor.account_name)
        if account is None or not account.board_identity:
            raise typer.BadParameter(f"{actor.account_name} has no board_identity")
        return str(account.board_identity)

    def adapter_for(actor: Any) -> AdoBoard:
        user = user_of(actor)
        if user not in tokens:
            raise typer.BadParameter(f"no board token for {user}: run make demo-reset")
        return AdoBoard(
            base_url=str(board_settings.board_url),
            organization=str(board_settings.board_organization),
            project=str(board_settings.board_project),
            token=tokens[user],
            public_url=board_settings.public_url(),
        )

    engagement = build(board_settings)
    coe = next(
        (
            Actor(a.account_name, a.roles)
            for a in accounts.values()
            if settings.deadletter_role in a.roles
        ),
        None,
    )

    def wait() -> None:
        drain()
        time.sleep(POLL_S)

    actor = BoardActor(
        engine,
        engagement.mapping,
        adapter_for=adapter_for,
        user_of=user_of,
        service_board=engagement.board,
        wait=wait,
    )

    def reconcile() -> dict[str, Any]:
        if coe is None:
            raise typer.BadParameter(f"no account holds the CoE role {settings.deadletter_role}")
        return engagement.reconciler.reconcile(coe)

    return actor, reconcile


@app.command()
def main(
    script: Annotated[Path, typer.Option(help="The demo script")] = Path("demo/script.yaml"),
    auto: Annotated[bool, typer.Option(help="Take the human steps too")] = False,
    live: Annotated[bool, typer.Option(help="Call the configured models")] = False,
    from_step: Annotated[int, typer.Option(help="Resume from this step")] = 1,
    profile: Annotated[str | None, typer.Option(help="Model profile with --live")] = None,
    references: Annotated[Path, typer.Option()] = Path("data/reference_usecases"),
    out: Annotated[Path | None, typer.Option(help="Also write the report here")] = None,
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
    board, reconcile = on_the_board(settings, stack.engine, orchestrator.drain)
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
        board=board,
        reconcile=reconcile,
    )
    report = driver.run(from_step)
    print(report.markdown(), flush=True)  # the wrapper keeps the output on the host
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(report.markdown())
        (out / "report.json").write_text(json.dumps(report.to_json(), indent=1, default=str))
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
