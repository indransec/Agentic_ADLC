"""Credential hashing with stdlib scrypt (research R-04).

Encoded form: ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``. Any value not in that form is a
placeholder and never verifies.
"""

import base64
import binascii
import hashlib
import hmac
import secrets

PREFIX = "scrypt"
N, R, P = 2**15, 8, 1
SALT_BYTES = 16
KEY_BYTES = 64
_MAXMEM = 128 * N * R * 2  # enough headroom for the parameters above


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(
        password.encode(), salt=salt, n=N, r=R, p=P, dklen=KEY_BYTES, maxmem=_MAXMEM
    )
    return "$".join(
        [
            PREFIX,
            str(N),
            str(R),
            str(P),
            base64.b64encode(salt).decode(),
            base64.b64encode(key).decode(),
        ]
    )


def is_placeholder(encoded: str) -> bool:
    return not encoded.startswith(PREFIX + "$")


def verify_password(password: str, encoded: str) -> bool:
    if is_placeholder(encoded):
        return False
    parts = encoded.split("$")
    if len(parts) != 6:
        return False
    try:
        n, r, p = (int(value) for value in parts[1:4])
        salt = base64.b64decode(parts[4], validate=True)
        expected = base64.b64decode(parts[5], validate=True)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=n, r=r, p=p, dklen=len(expected), maxmem=128 * n * r * 2
        )
    except (ValueError, binascii.Error):
        return False
    return hmac.compare_digest(actual, expected)


# A valid hash of a random value, used to spend the same time on unknown accounts.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
