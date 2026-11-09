"""``adlc-account``: hash a credential, check the account file (contracts/make-targets.md)."""

from getpass import getpass

import typer

from adlc.config.errors import load_settings_or_exit
from adlc.config.settings import Settings
from adlc.identity.accounts import AccountFileError, load_accounts
from adlc.identity.catalogue import CatalogueError, load_role_ids
from adlc.identity.hashing import hash_password

app = typer.Typer(add_completion=False, help="Local account tools for the ADLC platform.")


@app.command("hash")
def hash_command() -> None:
    """Prompt for a password twice (no echo) and print its scrypt hash only."""
    first = getpass("Password: ")
    second = getpass("Repeat password: ")
    if not first or first != second:
        typer.echo("Passwords are empty or do not match.", err=True)
        raise typer.Exit(1)
    typer.echo(hash_password(first))


@app.command("check")
def check_command() -> None:
    """Validate ADLC_ACCOUNTS_FILE against the role catalogue; in demo, placeholders fail."""
    settings = load_settings_or_exit(Settings)
    try:
        role_ids = load_role_ids(settings.role_catalogue)
        accounts = load_accounts(settings.accounts_file, role_ids, settings.env)
    except (CatalogueError, AccountFileError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    count = len(accounts)
    typer.echo(f"OK, {count} account{'s' if count != 1 else ''} ({settings.env})")
