"""`adlc-ledger` command line (contracts/verification.md).

``adlc-ledger verify [--usecase UC-nnnn] [--json]`` exits 0 when verified, 1 with breaks and
2 on a configuration error. Each call is recorded in ``ledger.verification_run`` with the actor
``cli:<os user>``.
"""

import getpass
import json
from typing import Annotated

import typer

SERVICE_NAME = "adlc-ledger"
app = typer.Typer(add_completion=False, help="Evidence ledger tools.")


@app.callback()
def main() -> None:
    """ADLC evidence ledger."""


@app.command("verify")
def verify_command(
    usecase: Annotated[
        str | None, typer.Option("--usecase", help="One use case (UC-nnnn); all when omitted")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON")] = False,
) -> None:
    """Recompute record, artifact and attachment hashes, the chain and package bindings."""
    from adlc.config.errors import load_settings_or_exit
    from adlc.config.settings import RuntimeSettings
    from adlc.db.engine import ConfigurationError, app_engine
    from adlc.ledger.storage import FileStore
    from adlc.ledger.verify import Verifier
    from adlc.observability.tracing import setup_process_tracing
    from adlc.spec_toolkit.registry import SqlSpecRegistry

    settings = load_settings_or_exit(RuntimeSettings)
    tracing = setup_process_tracing(SERVICE_NAME, settings)
    try:
        engine = app_engine(settings)
    except ConfigurationError as exc:
        typer.echo(f"adlc: configuration error\n  {exc}", err=True)
        raise typer.Exit(2) from None
    files = FileStore(
        settings.file_store_dir,
        max_bytes=settings.attachment_max,
        allowed_types=settings.attachment_types,
    )
    try:
        verifier = Verifier(engine, SqlSpecRegistry(engine), files.open)
        report = verifier.verify(usecase or "all", f"cli:{getpass.getuser()}")
    finally:
        engine.dispose()
        tracing.shutdown()  # flush the adlc.ledger.verify span before exiting
    if as_json:
        typer.echo(json.dumps(report.as_dict(), indent=2, default=str))
    else:
        typer.echo(
            f"{report.scope}: {report.records_checked} records checked, "
            f"{'verified' if report.verified else f'{len(report.breaks)} breaks'}"
        )
        if report.unscoped:
            typer.echo(
                f"  {len(report.unscoped)} records belong to no use case and cannot be verified: "
                + ", ".join(report.unscoped)
            )
        for b in report.breaks:
            typer.echo(
                f"  {b.ledger_key}  {b.check}  {b.element}: expected {b.expected}, got {b.actual}"
            )
    raise typer.Exit(0 if report.verified else 1)


@app.command("trace")
def trace_command(
    usecase: Annotated[str, typer.Argument(help="The use case (UC-nnnn)")],
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON")] = False,
) -> None:
    """014: every decision linked to spec version, actor and evidence hash; and the chain."""
    from adlc.config.errors import load_settings_or_exit
    from adlc.config.settings import RuntimeSettings
    from adlc.db.engine import app_engine
    from adlc.ledger.storage import FileStore
    from adlc.ledger.trace import trace
    from adlc.ledger.verify import Verifier
    from adlc.spec_toolkit.registry import SqlSpecRegistry

    settings = load_settings_or_exit(RuntimeSettings)
    engine = app_engine(settings)
    files = FileStore(
        settings.file_store_dir,
        max_bytes=settings.attachment_max,
        allowed_types=settings.attachment_types,
    )
    try:
        with engine.connect() as conn:
            report = trace(conn, usecase)
        verified = Verifier(engine, SqlSpecRegistry(engine), files.open).verify(
            usecase, f"cli:{getpass.getuser()}"
        )
    finally:
        engine.dispose()
    report["chain_verified"] = verified.verified
    if as_json:
        typer.echo(json.dumps(report, indent=2, default=str))
    else:
        counts = ", ".join(f"{k} {v}" for k, v in report["counts"].items())
        typer.echo(
            f"{usecase}: {counts}; {report['traceable']:.0%} traceable, "
            f"{len(report['gaps'])} gaps; chain {'verified' if verified.verified else 'BROKEN'}"
        )
        for gap in report["gaps"]:
            typer.echo(f"  gap: {gap['kind']} {gap['ref']} missing {', '.join(gap['missing'])}")
    if report["gaps"] or not verified.verified:
        raise typer.Exit(1)
