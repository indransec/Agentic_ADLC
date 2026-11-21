"""The board side of a demo reset (feature 020, research R-06; ``make demo-reset``).

After ``make up`` on a wiped stack the simulator is freshly seeded and holds no token. This
registers the board sync's token (``ADLC_BOARD_TOKEN`` in ``.env``) for the service account and
each demo person's token (the file at ``ADLC_DEMO_BOARD_TOKENS``, created when missing) with
``ado-sim token import`` over stdin. Tokens are never printed. The presenter signs in to the board's
pages with ``ADO_SIM_DEMO_PASSWORD``.

    uv run python -m scripts.demo_board
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from adlc.demo.tokens import TokensFileError, ensure_tokens
from adlc.identity.accounts import load_accounts
from adlc.identity.catalogue import load_role_ids

COMPOSE = ["docker", "compose", "-f", "deploy/compose.yaml", "--env-file", ".env"]
ROLES = Path("adlc-specs/shared/roles.yaml")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"demo-board: {name} must be set in .env for the demo on the board")
    return value


def board_people(accounts_file: Path, env: str) -> list[str]:
    """The board users of the accounts that act on the board (their ``board_identity``)."""
    accounts = load_accounts(accounts_file, load_role_ids(ROLES), env)
    return sorted({a.board_identity for a in accounts.values() if a.board_identity})


def register(user: str, token: str) -> None:
    """``ado-sim token import`` in the simulator's container; a token already there is fine."""
    done = subprocess.run(  # noqa: S603 - fixed command line; the token goes over stdin
        [*COMPOSE, "exec", "-T", "ado-sim", "ado-sim", "token", "import", user, "--stdin"],
        input=token + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0 and "already registered" not in done.stderr:
        raise SystemExit(f"demo-board: registering {user}'s token failed: {done.stderr.strip()}")


def main() -> int:
    if os.environ.get("ADLC_BOARD_ENABLED", "").lower() != "true":
        print("demo-board: the board sync is off (ADLC_BOARD_ENABLED); nothing to register")
        return 0
    service = _required("ADLC_BOARD_SERVICE_IDENTITY")
    tokens_file = Path(_required("ADLC_DEMO_BOARD_TOKENS")).expanduser()
    if not os.environ.get("ADO_SIM_DEMO_PASSWORD"):
        print(
            "demo-board: ADO_SIM_DEMO_PASSWORD is empty: the presenter cannot sign in to the board"
        )
    people = board_people(Path(_required("ADLC_ACCOUNTS_FILE")), _required("ADLC_ENV"))
    try:
        tokens = ensure_tokens(tokens_file, people)
    except TokensFileError as error:
        raise SystemExit(f"demo-board: {error}") from None
    register(service, _required("ADLC_BOARD_TOKEN"))
    for user in people:
        register(user, tokens[user])
    print(f"demo-board: registered the sync's token and {len(people)} demo people's tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
