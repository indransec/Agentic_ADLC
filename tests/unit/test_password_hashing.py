"""US4: credential hashing (research R-04)."""

import re

from adlc.identity.hashing import hash_password, is_placeholder, verify_password

ENCODED = re.compile(r"^scrypt\$32768\$8\$1\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+$")


def test_hash_format() -> None:
    assert ENCODED.match(hash_password("correct horse battery staple"))


def test_verify_right_and_wrong() -> None:
    encoded = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", encoded)
    assert not verify_password("s3cret-pasS", encoded)


def test_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_placeholders() -> None:
    for value in ("REPLACE_WITH_HASH", "", "bcrypt$abc", "scrypt"):
        assert is_placeholder(value)
        assert not verify_password("anything", value)
    assert not is_placeholder(hash_password("x"))


def test_malformed_scrypt_value_never_verifies() -> None:
    assert not verify_password("x", "scrypt$1$2$3$!!$!!")
    assert not verify_password("x", "scrypt$abc")
