"""The enterprise directory for ``in_directory`` (research R-10).

The account file is the MVP directory; the orchestrator mounts it read-only. Without it, the
directory is not available and the check fails closed (or the synthetic provider supplies it).
"""

from pathlib import Path
from typing import Protocol

from adlc.identity.accounts import load_accounts
from adlc.identity.catalogue import load_role_ids


class Directory(Protocol):
    def names(self) -> frozenset[str] | None: ...


class UnavailableDirectory:
    def names(self) -> frozenset[str] | None:
        return None


class AccountFileDirectory:
    def __init__(self, accounts_file: Path, role_catalogue: Path, env: str) -> None:
        self.accounts_file = accounts_file
        self.role_catalogue = role_catalogue
        self.env = env

    def names(self) -> frozenset[str] | None:
        accounts = load_accounts(self.accounts_file, load_role_ids(self.role_catalogue), self.env)
        return frozenset(accounts)
