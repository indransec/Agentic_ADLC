"""Identity interface (contracts/identity-provider.md, FR-017, constitution VII).

Callers depend only on this Protocol; the local-account implementation can be replaced by an
OIDC one through configuration and one adapter.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import SecretStr


@dataclass(frozen=True)
class Person:
    account_name: str
    display_name: str
    roles: frozenset[str]


@dataclass(frozen=True)
class SessionGrant:
    token: str
    expires_at: datetime
    person: Person


class InvalidCredentials(Exception):
    """Unknown account, wrong password or placeholder credential (deliberately one type)."""


class NotAuthenticated(Exception):
    """Missing, malformed, wrongly signed, expired or revoked session."""


class UnknownAccount(Exception):
    """The account no longer exists."""


class IdentityProvider(Protocol):
    def sign_in(self, account_name: str, password: SecretStr) -> SessionGrant: ...

    def current_person(self, token: str) -> Person: ...

    def roles(self, account_name: str) -> frozenset[str]: ...

    def sign_out(self, token: str) -> None: ...
