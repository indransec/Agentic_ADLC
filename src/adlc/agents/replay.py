"""``adlc-replay``: replays the reference use cases through the grounded terminals (008 T029)."""

import typer

app = typer.Typer(help="Replay the reference use cases through the grounded terminals.")


@app.command()
def run() -> None:
    """Placeholder until task T029."""
    raise typer.Exit(2)
