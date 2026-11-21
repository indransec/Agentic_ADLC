"""Board users ↔ platform accounts (T018, FR-013, research R-11)."""

from pathlib import Path

import pytest

from adlc.engagement.identities import BoardIdentities, IdentityConfigError
from adlc.identity.hashing import hash_password

ROLES = frozenset({"business_owner", "product_owner", "adlc_coe"})
HASH = hash_password("pw-for-tests")
SERVICE = "service@board.test"


def _accounts(tmp_path: Path, *entries: tuple[str, str, str | None]) -> Path:
    lines = ["accounts:"]
    for name, role, identity in entries:
        lines += [
            f"  - account_name: {name}",
            "    display_name: Demo Person",
            f"    roles: [{role}]",
            f"    credential_hash: '{HASH}'",
        ]
        if identity is not None:
            lines.append(f"    board_identity: {identity}")
    path = tmp_path / "accounts.yaml"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_maps_board_users_to_actors(tmp_path: Path) -> None:
    path = _accounts(
        tmp_path,
        ("owner.business", "business_owner", "Business.Owner@board.test"),
        ("owner.product", "product_owner", None),
    )
    identities = BoardIdentities.load(path, ROLES, "dev", SERVICE)
    actor = identities.actor("business.owner@BOARD.test")
    assert actor is not None
    assert actor.account_name == "owner.business"
    assert actor.roles == frozenset({"business_owner"})
    assert actor.kind == "human"
    assert identities.display_name("business.owner@board.test") == "Demo Person"
    assert identities.actor("owner.product@board.test") is None  # no board identity: cannot act
    assert identities.actor("someone@board.test") is None


def test_the_service_account_never_maps(tmp_path: Path) -> None:
    path = _accounts(tmp_path, ("owner.business", "business_owner", "business.owner@board.test"))
    identities = BoardIdentities.load(path, ROLES, "dev", SERVICE.upper())
    assert identities.is_service(SERVICE)
    assert identities.actor(SERVICE) is None


def test_an_account_claiming_the_service_identity_is_refused(tmp_path: Path) -> None:
    path = _accounts(tmp_path, ("owner.business", "business_owner", SERVICE))
    with pytest.raises(IdentityConfigError, match="owner.business"):
        BoardIdentities.load(path, ROLES, "dev", SERVICE)
