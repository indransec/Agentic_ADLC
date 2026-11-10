"""`adlc-spec` command line (contracts/adlc-spec-cli.md)."""

import os
import time
from pathlib import Path
from typing import Annotated, Literal

import typer

from adlc.spec_toolkit.findings import Report
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.rules import Context, validate

app = typer.Typer(add_completion=False, help="Validate and register ADLC terminal specs.")

DEFAULT_BASELINE = "origin/main"


def run_validation(
    path: Path, baseline_ref: str | None, use_git: bool
) -> tuple[Report, list[object]]:
    started = time.monotonic()
    bundle = load_bundle(path)
    findings = validate(Context(bundle, baseline_ref=baseline_ref, use_git_baseline=use_git))
    report = Report(findings, files=len(bundle.files()), seconds=time.monotonic() - started)
    return report, [bundle]


@app.callback()
def main() -> None:
    """ADLC spec toolkit."""


@app.command("validate")
def validate_command(
    path: Annotated[Path, typer.Argument(help="Spec folder")] = Path("adlc-specs"),
    output_format: Annotated[
        Literal["text", "json"], typer.Option("--format", help="Output format")
    ] = "text",
    baseline_ref: Annotated[
        str | None, typer.Option("--baseline-ref", help="Git ref for L5 (version bumps)")
    ] = None,
    no_baseline: Annotated[bool, typer.Option("--no-baseline", help="Skip L5 against git")] = False,
    min_severity: Annotated[
        Literal["error", "warning", "info"], typer.Option("--min-severity")
    ] = "info",
) -> None:
    """Validate the spec folder at L1–L5."""
    if not path.is_dir():
        typer.echo(f"adlc-spec: {path} is not a directory", err=True)
        raise typer.Exit(2)
    ref = (
        None
        if no_baseline
        else (baseline_ref or os.environ.get("ADLC_SPEC_BASELINE_REF") or DEFAULT_BASELINE)
    )
    report, _ = run_validation(path, ref, use_git=ref is not None)
    if output_format == "json":
        typer.echo(report.to_json(min_severity))
    else:
        typer.echo(report.to_text(min_severity))
    raise typer.Exit(1 if report.has_errors else 0)


@app.command("register")
def register_command(
    path: Annotated[Path, typer.Argument(help="Spec folder")] = Path("adlc-specs"),
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Plan, then roll back")] = False,
) -> None:
    """Validate, then register specs into the ADLC_DB_* data store (schema-owner identity)."""
    from adlc.config.errors import load_settings_or_exit
    from adlc.config.settings import DatabaseSettings
    from adlc.db.engine import ConfigurationError, owner_engine
    from adlc.spec_toolkit.register import RegistrationRefused, register

    if not path.is_dir():
        typer.echo(f"adlc-spec: {path} is not a directory", err=True)
        raise typer.Exit(2)
    settings = load_settings_or_exit(DatabaseSettings)
    try:
        engine = owner_engine(settings)
    except ConfigurationError as exc:
        typer.echo(f"adlc: configuration error\n  {exc}", err=True)
        raise typer.Exit(2) from None
    try:
        report = register(path, engine, dry_run=dry_run)
    except RegistrationRefused as exc:
        typer.echo(f"spec registration refused, nothing written: {exc}", err=True)
        raise typer.Exit(1) from None
    finally:
        engine.dispose()
    for line in report.lines():
        typer.echo(line)
