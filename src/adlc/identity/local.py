"""Local-account identity provider for the MVP (SA §11, research R-04, R-05)."""

import logging
from datetime import timedelta
from pathlib import Path

from pydantic import SecretStr

from adlc.identity.accounts import Account, load_accounts
from adlc.identity.catalogue import load_role_ids
from adlc.identity.hashing import DUMMY_HASH, verify_password
from adlc.identity.protocol import (
    InvalidCredentials,
    NotAuthenticated,
    Person,
    SessionGrant,
    UnknownAccount,
)
from adlc.identity.sessions import Clock, RevocationSet, SessionError, SessionSigner, utc_now

log = logging.getLogger("adlc.identity")


class LocalIdentityProvider:
    def __init__(
        self,
        accounts: dict[str, Account],
        session_secret: str,
        session_ttl: timedelta,
        clock: Clock = utc_now,
    ) -> None:
        self._accounts = accounts
        self._signer = SessionSigner(session_secret, session_ttl, clock=clock)
        self._revoked = RevocationSet(clock=clock)

    @classmethod
    def from_files(
        cls,
        accounts_file: Path,
        role_catalogue: Path,
        env: str,
        session_secret: str,
        session_ttl: timedelta,
    ) -> "LocalIdentityProvider":
        role_ids = load_role_ids(role_catalogue)
        return cls(load_accounts(accounts_file, role_ids, env), session_secret, session_ttl)

    def _person(self, account: Account) -> Person:
        return Person(account.account_name, account.display_name, account.roles)

    def sign_in(self, account_name: str, password: SecretStr) -> SessionGrant:
        account = self._accounts.get(account_name)
        encoded = account.credential_hash if account is not None else DUMMY_HASH
        valid = verify_password(password.get_secret_value(), encoded)
        if account is None or not account.can_sign_in or not valid:
            log.info("auth.sign_in account_name=%r outcome=refused", account_name)
            raise InvalidCredentials
        token, expires_at = self._signer.issue(account.account_name)
        log.info("auth.sign_in account_name=%r outcome=success", account.account_name)
        return SessionGrant(token=token, expires_at=expires_at, person=self._person(account))

    def current_person(self, token: str) -> Person:
        try:
            claims = self._signer.verify(token)
        except SessionError:
            raise NotAuthenticated from None
        if claims.session_id in self._revoked:
            raise NotAuthenticated
        account = self._accounts.get(claims.account_name)
        if account is None:
            raise NotAuthenticated
        return self._person(account)

    def roles(self, account_name: str) -> frozenset[str]:
        account = self._accounts.get(account_name)
        if account is None:
            raise UnknownAccount(account_name)
        return account.roles

    def sign_out(self, token: str) -> None:
        try:
            claims = self._signer.verify(token)
        except SessionError:
            return
        self._revoked.add(claims.session_id, claims.expires_at)
        log.info("auth.sign_out account_name=%r", claims.account_name)
