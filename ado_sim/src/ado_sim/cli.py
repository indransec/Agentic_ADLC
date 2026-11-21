"""Operator commands: ``ado-sim migrate | seed | reset | token | serve | export-openapi``.

Exit codes (contracts/cli-settings-seed.md): 0 done, 1 refused, 2 settings or invalid input.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from pathlib import Path

from ado_sim import auth
from ado_sim.db import LATEST_VERSION, Database, DatabaseMissingError, migrate, schema_version
from ado_sim.pages import sessions, signin
from ado_sim.seed import SeedError, SeedRefusedError, is_seeded, load_seed
from ado_sim.settings import Settings, SettingsError, load_settings

OK, REFUSED, INVALID = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ado-sim", description="ADO simulator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="create the database if missing and apply migrations")
    seed = commands.add_parser("seed", help="load a seed file into an empty database")
    seed.add_argument("--file", type=Path, required=True)
    seed.add_argument("--if-new", action="store_true", help="do nothing if already seeded")
    reset = commands.add_parser("reset", help="remove all data and seed from ADO_SIM_SEED_FILE")
    reset.add_argument("--yes", action="store_true", help="confirm that all data is removed")
    token = commands.add_parser("token", help="personal access tokens")
    token_commands = token.add_subparsers(dest="action", required=True)
    issue = token_commands.add_parser("issue", help="print a new token for an identity, once")
    issue.add_argument("unique_name")
    issue.add_argument("--label", default="")
    imported = token_commands.add_parser(
        "import", help="register a token read from stdin (020: demo resets; not in ADO)"
    )
    imported.add_argument("unique_name")
    imported.add_argument("--stdin", action="store_true", required=True)
    imported.add_argument("--label", default="imported")
    revoke = token_commands.add_parser("revoke", help="revoke a token by id")
    revoke.add_argument("token_id", type=int)
    listing = token_commands.add_parser("list", help="list tokens (never the tokens themselves)")
    listing.add_argument("unique_name", nargs="?")
    password = commands.add_parser("password", help="page sign-in passwords (feature 017)")
    password_commands = password.add_subparsers(dest="action", required=True)
    set_password = password_commands.add_parser("set", help="set a page password (asked twice)")
    who = set_password.add_mutually_exclusive_group(required=True)
    who.add_argument("unique_name", nargs="?")
    who.add_argument("--all", action="store_true", help="the same password for every demo user")
    set_password.add_argument("--stdin", action="store_true", help="read it once from stdin")
    clear = password_commands.add_parser("clear", help="remove a page password; ends sessions")
    clear.add_argument("unique_name")
    commands.add_parser("serve", help="run the API and the pages")
    export = commands.add_parser("export-openapi", help="write or check contract/openapi.json")
    export.add_argument("--check", action="store_true")
    export.add_argument("--output", type=Path, default=Path("contract/openapi.json"))
    return parser


def _ready_database(settings: Settings) -> Database:
    db = Database(settings.db_path, settings.busy_timeout_seconds)
    if schema_version(db) != LATEST_VERSION:
        db.close()
        raise DatabaseMissingError(
            f"the database at {settings.db_path} is not migrated; run `ado-sim migrate`"
        )
    return db


def _reset(settings: Settings) -> None:
    from ado_sim.db import drop_everything

    db = Database(settings.db_path, settings.busy_timeout_seconds, create=True)
    try:
        drop_everything(db)
        migrate(db)
        load_seed(db, settings.seed_file)
    finally:
        db.close()


def _export_openapi(output: Path, check: bool) -> int:
    from ado_sim.app import openapi_text

    text = openapi_text()
    if check:
        current = output.read_text(encoding="utf-8") if output.exists() else ""
        if current != text:
            print(f"{output} differs from the served contract; run `ado-sim export-openapi`")
            return REFUSED
        print(f"{output} is up to date")
        return OK
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"wrote {output}")
    return OK


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "export-openapi":
        return _export_openapi(args.output, args.check)
    try:
        settings = load_settings()
    except SettingsError as error:
        print(f"settings error: {error}", file=sys.stderr)
        return INVALID
    try:
        if args.command == "migrate":
            db = Database(settings.db_path, settings.busy_timeout_seconds, create=True)
            applied = migrate(db)
            db.close()
            print(f"applied migrations {applied}" if applied else "database is up to date")
            return OK
        if args.command == "reset":
            if not args.yes:
                print("reset removes every work item, comment and token; add --yes to confirm")
                return REFUSED
            _reset(settings)
            print(f"reset and seeded from {settings.seed_file}")
            return OK
        db = _ready_database(settings)
        try:
            return _run_with_database(args, settings, db)
        finally:
            db.close()
    except DatabaseMissingError as error:
        print(str(error), file=sys.stderr)
        return INVALID
    except SeedRefusedError as error:
        print(f"seed refused: {error}", file=sys.stderr)
        return REFUSED
    except SeedError as error:
        print(f"invalid seed file: {error}", file=sys.stderr)
        return INVALID


def _run_with_database(args: argparse.Namespace, settings: Settings, db: Database) -> int:
    if args.command == "seed":
        if args.if_new and is_seeded(db):
            print("already seeded; nothing to do")
            return OK
        seed = load_seed(db, args.file)
        print(f"seeded {seed.organization}/{seed.project} from {args.file}")
        return OK
    if args.command == "token":
        if args.action == "issue":
            try:
                token_id, token = auth.issue(db, settings.token_key, args.unique_name, args.label)
            except auth.TokenError as error:
                print(str(error), file=sys.stderr)
                return REFUSED
            print(f"token id {token_id} for {args.unique_name} (shown once, store it now):")
            print(token)
            return OK
        if args.action == "import":
            try:
                given = sys.stdin.readline().strip()
                token_id = auth.import_token(
                    db, settings.token_key, args.unique_name, given, args.label
                )
            except auth.TokenError as error:
                print(str(error), file=sys.stderr)
                return REFUSED
            print(f"token id {token_id} registered for {args.unique_name}")
            return OK
        if args.action == "revoke":
            owner = _token_owner(db, args.token_id)
            if not auth.revoke(db, args.token_id):
                print(f"no active token with id {args.token_id}", file=sys.stderr)
                return REFUSED
            ended = sessions.revoke_all(db, owner) if owner else 0  # 017 FR-004a
            print(f"revoked token {args.token_id}; ended {ended} page session(s)")
            return OK
        for info in auth.list_tokens(db, args.unique_name):
            status = f"revoked {info.revoked_at}" if info.revoked_at else "active"
            print(f"{info.id}\t{info.unique_name}\t{info.label}\tissued {info.issued_at}\t{status}")
        return OK
    if args.command == "password":
        return _password(args, db)
    # serve
    import uvicorn

    from ado_sim.app import create_app

    db.close()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    return OK


def _token_owner(db: Database, token_id: int) -> str | None:
    with db.read() as conn:
        row = conn.execute(
            "SELECT identity_id FROM access_token WHERE id = ?", (token_id,)
        ).fetchone()
    return None if row is None else str(row[0])


def _read_password(from_stdin: bool) -> str | None:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("page password: ")
    if first != getpass.getpass("again: "):
        print("the two passwords differ", file=sys.stderr)
        return None
    return first


def _password(args: argparse.Namespace, db: Database) -> int:
    if args.action == "clear":
        if not signin.clear_password(db, args.unique_name):
            print(f"{args.unique_name} has no page password", file=sys.stderr)
            return REFUSED
        print(f"cleared the page password of {args.unique_name}; their page sessions ended")
        return OK
    password = _read_password(args.stdin)
    if password is None:
        return INVALID
    if len(password) < signin.MIN_PASSWORD_LENGTH:
        print(
            f"a page password needs at least {signin.MIN_PASSWORD_LENGTH} characters",
            file=sys.stderr,
        )
        return INVALID
    if args.all:
        with db.read() as conn:
            names = [
                r[0]
                for r in conn.execute(
                    "SELECT unique_name FROM identity WHERE is_service = 0 AND active = 1"
                    " ORDER BY unique_name"
                )
            ]
        for name in names:
            signin.set_password(db, name, password)
        print(f"set the page password of {len(names)} users")
        return OK
    try:
        signin.set_password(db, args.unique_name, password)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return REFUSED
    print(f"set the page password of {args.unique_name}")
    return OK


def main() -> None:
    sys.exit(run())
