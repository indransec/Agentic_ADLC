"""T006: run tokens (contracts/run-token.md): one run, its scopes, five minutes."""

import base64
import json

import pytest

from adlc.tools.token import TTL_S, Claims, TokenError, issue, sign, verify

KEY = "k" * 40
NOW = 1_800_000_000.0


def claims(**over: object) -> Claims:
    values: dict[str, object] = {
        "run_id": "UC-0001/T3/run-1",
        "usecase_id": "UC-0001",
        "terminal_id": "T3",
        "attempt": 1,
        "scopes": ("mcp:pilot_env:dev", "mcp:git:branch_write"),
        "bound": {"environment": "dev", "branch": "uc/UC-0001/UC-0001-T3-run-1"},
        "now": NOW,
    }
    values.update(over)
    return issue(**values)  # type: ignore[arg-type]


def test_round_trip_and_lifetime() -> None:
    token = sign(claims(), KEY)
    got = verify(token, KEY, scope="mcp:pilot_env:dev", now=NOW + 10)
    assert got.run_id == "UC-0001/T3/run-1" and got.bound["environment"] == "dev"
    assert got.exp - got.iat == TTL_S == 300


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda t: t.replace("v1.", "v2.", 1), "malformed"),
        (lambda t: t + "x", "signature"),
        (lambda t: "v1.e30." + t.split(".")[2], "signature"),
        (lambda t: "garbage", "malformed"),
    ],
)
def test_tampering_is_refused(mutate: object, reason: str) -> None:
    token = sign(claims(), KEY)
    with pytest.raises(TokenError, match=reason):
        verify(mutate(token), KEY, scope="mcp:pilot_env:dev", now=NOW)  # type: ignore[operator]


def test_wrong_key_expired_future_and_scope() -> None:
    token = sign(claims(), KEY)
    with pytest.raises(TokenError, match="signature"):
        verify(token, "z" * 40, scope="mcp:pilot_env:dev", now=NOW)
    with pytest.raises(TokenError, match="expired"):
        verify(token, KEY, scope="mcp:pilot_env:dev", now=NOW + TTL_S + 1)
    with pytest.raises(TokenError, match="future"):
        verify(sign(claims(now=NOW + 120), KEY), KEY, scope="mcp:pilot_env:dev", now=NOW)
    with pytest.raises(TokenError, match="not granted"):
        verify(token, KEY, scope="mcp:pilot_env:test", now=NOW)


def test_required_bound_values() -> None:
    token = sign(claims(bound={}), KEY)
    with pytest.raises(TokenError, match="authorised_hash"):
        verify(token, KEY, scope="mcp:pilot_env:dev", now=NOW, required=("authorised_hash",))


def test_canonical_claims_and_no_token_in_errors() -> None:
    token = sign(claims(), KEY)
    body = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert list(body) == sorted(body)
    with pytest.raises(TokenError) as error:
        verify(token, KEY, scope="mcp:x:y", now=NOW)
    assert token not in str(error.value) and token.split(".")[2] not in str(error.value)


def test_short_key_is_refused() -> None:
    with pytest.raises(ValueError, match="32"):
        sign(claims(), "short")
