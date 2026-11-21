"""The demo people's board tokens (feature 020, research R-06).

The demo driver acts on the board as each demo person with that person's personal access token.
A demo reset wipes the simulator, so the tokens are kept in a file outside the repository
(``ADLC_DEMO_BOARD_TOKENS``) and registered again after every reset (``ado-sim token import``).
The file is created with random tokens when missing, readable by its owner only (0600), and its
tokens are never printed or logged.
"""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Iterable
from pathlib import Path

from ruamel.yaml import YAML

MODE = 0o600


class TokensFileError(ValueError):
    """The tokens file is missing, unreadable, malformed or not private; names the file only."""


def _new() -> str:
    return secrets.token_urlsafe(36)  # 48 characters


def read_tokens(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise TokensFileError(f"no tokens file at {path} (make demo-reset creates it)")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise TokensFileError(f"{path} must be readable by its owner only (chmod 0600)")
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if not isinstance(tokens, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in tokens.items()
    ):
        raise TokensFileError(f"{path}: 'tokens' must map each board user to token")
    return {str(k).lower(): str(v) for k, v in tokens.items()}


def ensure_tokens(path: Path, users: Iterable[str]) -> dict[str, str]:
    """The tokens of ``users``, adding a random one for each user the file does not have yet."""
    tokens = read_tokens(path) if path.exists() else {}
    wanted = [u.lower() for u in users]
    if all(u in tokens for u in wanted) and path.exists():
        return {u: tokens[u] for u in wanted}
    for user in wanted:
        tokens.setdefault(user, _new())
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("# Demo board tokens (feature 020): secret; never commit or print.\n")
        YAML().dump({"tokens": dict(sorted(tokens.items()))}, handle)
    path.chmod(MODE)
    return {u: tokens[u] for u in wanted}
