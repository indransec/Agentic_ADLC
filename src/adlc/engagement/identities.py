"""Board users ↔ platform accounts (FR-013; research R-11).

A board change is attributed to the board user who made it; before any decision right is checked
that user must map to an account in the accounts file through the account's ``board_identity``
(compared lower-cased). Roles come from the account (and so from ``roles.yaml``). The platform's
service account never maps to an account, so its own writes are never read as a person's request.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from adlc.identity.accounts import Account, load_accounts
from adlc.orchestration.service import Actor


class IdentityConfigError(ValueError):
    """The accounts file and the board settings disagree (an account claims the service
    identity)."""


class BoardIdentities:
    def __init__(self, accounts: Mapping[str, Account], service_identity: str) -> None:
        self.service_identity = service_identity.lower()
        self._by_identity: dict[str, Account] = {}
        for account in accounts.values():
            if account.board_identity is None:
                continue
            if account.board_identity == self.service_identity:
                raise IdentityConfigError(
                    f"account {account.account_name} claims the board service account's identity; "
                    "the service account must not be a person's board identity"
                )
            self._by_identity[account.board_identity] = account

    @classmethod
    def load(
        cls, path: Path, role_ids: frozenset[str], env: str, service_identity: str
    ) -> BoardIdentities:
        return cls(load_accounts(path, role_ids, env), service_identity)

    def is_service(self, unique_name: str) -> bool:
        return unique_name.lower() == self.service_identity

    def actor(self, unique_name: str) -> Actor | None:
        """The platform actor for a board user, or None when the user maps to no account."""
        if self.is_service(unique_name):
            return None
        account = self._by_identity.get(unique_name.lower())
        if account is None:
            return None
        return Actor(account.account_name, account.roles, "human")

    def display_name(self, unique_name: str) -> str | None:
        account = self._by_identity.get(unique_name.lower())
        return None if account is None else account.display_name
