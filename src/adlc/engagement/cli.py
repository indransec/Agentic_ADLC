"""``adlc-board``: run the board sync, check the mapping, reconcile, health, requeue (feature 016;
contracts/api-cli-settings.md "Commands"). Exit codes: 0 done, 1 refused or gaps, 2 settings."""

from __future__ import annotations

import json
import signal
import threading
from types import FrameType
from typing import Any

import typer

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import BoardSettings
from adlc.db.engine import DatabaseUnavailable, open_engine, wait_for_database
from adlc.engagement.health import health as sync_health
from adlc.engagement.port import BoardError
from adlc.engagement.wiring import BoardDisabled, Engagement, build
from adlc.engagement.worker import BoardWorker, serve_health
from adlc.identity.accounts import load_accounts
from adlc.identity.catalogue import load_role_ids
from adlc.observability.logging import configure_logging
from adlc.observability.tracing import setup_process_tracing
from adlc.orchestration.interfaces import SystemClock
from adlc.orchestration.service import Actor, NotAuthorised

app = typer.Typer(
    add_completion=False,
    help="Board engagement (feature 016): sync the platform with a tracker board.",
)
SERVICE_NAME = "adlc-board"
REFUSED, SETTINGS = 1, 2


def _settings() -> BoardSettings:
    settings = load_settings_or_exit(BoardSettings)
    configure_logging(settings.log_level)
    return settings


def _engagement(settings: BoardSettings) -> Engagement:
    try:
        return build(settings)
    except BoardDisabled as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(SETTINGS) from None


def _actor(settings: BoardSettings, account_name: str) -> Actor:
    accounts = load_accounts(
        settings.accounts_file, load_role_ids(settings.role_catalogue), settings.env
    )
    account = accounts.get(account_name)
    if account is None:
        typer.echo(f"no account {account_name} in the accounts file", err=True)
        raise typer.Exit(REFUSED)
    return Actor(account.account_name, account.roles)


def _print(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, default=str))


@app.command("run")
def run() -> None:
    """The sync process: check the mapping, then poll and project until stopped."""
    settings = _settings()
    stop = threading.Event()

    def _stop(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    if not settings.board_enabled:
        serve_health(settings.board_port, lambda: {"status": "disabled"})
        typer.echo("board sync is disabled (ADLC_BOARD_ENABLED is not true); serving /health only")
        stop.wait()
        return
    engine = open_engine(settings)
    try:
        wait_for_database(engine, settings.db_connect_timeout)
    except DatabaseUnavailable as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(SETTINGS) from None
    setup_process_tracing(SERVICE_NAME, settings)
    worker = BoardWorker(_engagement(settings))
    serve_health(settings.board_port, lambda: {"status": worker.status, "gaps": worker.gaps})
    worker.run_forever(stop)


@app.command("check-mapping")
def check_mapping() -> None:
    """Check the tracker mapping against the board; list every gap."""
    settings = _settings()
    engagement = _engagement(settings)
    try:
        gaps = engagement.mapping.check_against(engagement.board.check())
    except BoardError as error:
        typer.echo(f"the board cannot be checked: {type(error).__name__}: {error}", err=True)
        raise typer.Exit(REFUSED) from None
    for gap in gaps:
        typer.echo(gap)
    if gaps:
        raise typer.Exit(REFUSED)
    typer.echo("the tracker mapping fits the board")


@app.command("reconcile")
def reconcile(account: str = typer.Option(..., "--as", help="the CoE account running it")) -> None:
    """Make the board match the platform now; print the report."""
    settings = _settings()
    engagement = _engagement(settings)
    try:
        _print(engagement.reconciler.reconcile(_actor(settings, account)))
    except NotAuthorised as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(REFUSED) from None


@app.command("health")
def health() -> None:
    """Print sync health (works with the board disabled)."""
    settings = _settings()
    engine = open_engine(settings)
    _print(sync_health(engine, enabled=settings.board_enabled, now=SystemClock().now()))


@app.command("requeue")
def requeue(
    usecase_id: str, account: str = typer.Option(..., "--as", help="the CoE account")
) -> None:
    """Requeue a dead-lettered use case's projection."""
    settings = _settings()
    actor = _actor(settings, account)
    if not settings.deadletter_role or settings.deadletter_role not in actor.roles:
        typer.echo(f"requeue needs the role {settings.deadletter_role}", err=True)
        raise typer.Exit(REFUSED)
    engagement = _engagement(settings)
    if not engagement.projector.requeue(usecase_id, actor.account_name):
        typer.echo(f"the board projection of {usecase_id} is not dead-lettered", err=True)
        raise typer.Exit(REFUSED)
    typer.echo(f"requeued {usecase_id}")
