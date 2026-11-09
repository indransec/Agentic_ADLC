"""US4: signed, expiring session tokens with in-process revocation (research R-05)."""

from datetime import UTC, datetime, timedelta

import pytest

from adlc.identity.sessions import RevocationSet, SessionError, SessionSigner

SECRET = "unit-test-session-secret-" + "z" * 16
TTL = timedelta(hours=8)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def test_issue_and_verify() -> None:
    signer = SessionSigner(SECRET, TTL)
    token, expires_at = signer.issue("owner.business")
    claims = signer.verify(token)
    assert claims.account_name == "owner.business"
    assert len(claims.session_id) == 32
    assert expires_at - claims.issued_at == TTL


def test_tampered_token_refused() -> None:
    signer = SessionSigner(SECRET, TTL)
    token, _ = signer.issue("owner.business")
    with pytest.raises(SessionError):
        signer.verify(token[:-2] + ("aa" if not token.endswith("aa") else "bb"))
    with pytest.raises(SessionError):
        signer.verify("garbage")


def test_other_secret_refused() -> None:
    token, _ = SessionSigner(SECRET, TTL).issue("owner.business")
    with pytest.raises(SessionError):
        SessionSigner("another-secret-" + "q" * 20, TTL).verify(token)


def test_expired_token_refused() -> None:
    clock = Clock()
    signer = SessionSigner(SECRET, TTL, clock=clock)
    token, _ = signer.issue("owner.business")
    clock.now += TTL - timedelta(seconds=1)
    signer.verify(token)
    clock.now += timedelta(seconds=2)
    with pytest.raises(SessionError):
        signer.verify(token)


def test_revocation_until_expiry() -> None:
    clock = Clock()
    revoked = RevocationSet(clock=clock)
    revoked.add("abc", clock.now + timedelta(minutes=5))
    assert "abc" in revoked
    clock.now += timedelta(minutes=6)
    assert "abc" not in revoked
    assert len(revoked) == 0
