"""US4: account file validation (FR-018, FR-019, contracts/files.md)."""

from pathlib import Path

import pytest

from adlc.identity.accounts import AccountFileError, load_accounts
from adlc.identity.hashing import hash_password

ROLES = frozenset({"business_owner", "product_owner", "adlc_coe"})
HASH = hash_password("pw-for-tests")


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "accounts.yaml"
    path.write_text(body)
    return path


def _account(
    name: str = "owner.business", roles: str = "[business_owner]", cred: str = HASH
) -> str:
    return (
        f"  - account_name: {name}\n"
        f"    display_name: Demo Person\n"
        f"    roles: {roles}\n"
        f"    credential_hash: '{cred}'\n"
    )


def test_valid_file_loads(tmp_path: Path) -> None:
    path = _write(tmp_path, "accounts:\n" + _account(roles="[business_owner, product_owner]"))
    accounts = load_accounts(path, ROLES, "demo")
    account = accounts["owner.business"]
    assert account.roles == frozenset({"business_owner", "product_owner"})
    assert account.can_sign_in


def test_empty_list_loads(tmp_path: Path) -> None:
    assert load_accounts(_write(tmp_path, "accounts: []\n"), ROLES, "dev") == {}


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("accounts:\n" + _account(roles="[nobody_role]"), "owner.business.*nobody_role"),
        ("accounts:\n" + _account(roles="[]"), "owner.business"),
        ("accounts:\n" + _account() + _account(), "duplicate.*owner.business"),
        ("accounts:\n" + _account(name="Bad Name"), "Bad Name"),
        ("accounts:\n" + _account() + "    extra_key: 1\n", "owner.business.*extra_key"),
        ("other: 1\n", "accounts"),
    ],
)
def test_invalid_files_name_the_account(tmp_path: Path, body: str, fragment: str) -> None:
    with pytest.raises(AccountFileError, match=fragment):
        load_accounts(_write(tmp_path, body), ROLES, "dev")


def test_placeholder_refused_in_demo(tmp_path: Path) -> None:
    path = _write(tmp_path, "accounts:\n" + _account(cred="REPLACE_WITH_HASH"))
    with pytest.raises(AccountFileError, match="owner.business.*placeholder"):
        load_accounts(path, ROLES, "demo")


def test_placeholder_loads_in_dev_but_cannot_sign_in(tmp_path: Path) -> None:
    path = _write(tmp_path, "accounts:\n" + _account(cred="REPLACE_WITH_HASH"))
    account = load_accounts(path, ROLES, "dev")["owner.business"]
    assert not account.can_sign_in


def test_error_never_contains_credential_hash(tmp_path: Path) -> None:
    path = _write(tmp_path, "accounts:\n" + _account(roles="[nobody_role]"))
    with pytest.raises(AccountFileError) as excinfo:
        load_accounts(path, ROLES, "dev")
    assert HASH not in str(excinfo.value)


# ------------------------------------------------------------------ 016 board identity


def _with_identity(name: str, identity: str) -> str:
    return _account(name) + f"    board_identity: {identity}\n"


def test_board_identity_is_optional(tmp_path: Path) -> None:
    accounts = load_accounts(_write(tmp_path, "accounts:\n" + _account()), ROLES, "dev")
    assert accounts["owner.business"].board_identity is None


def test_board_identity_loads_lower_cased(tmp_path: Path) -> None:
    body = "accounts:\n" + _with_identity("owner.business", "Business.Owner@Example.Test")
    account = load_accounts(_write(tmp_path, body), ROLES, "dev")["owner.business"]
    assert account.board_identity == "business.owner@example.test"


@pytest.mark.parametrize("identity", ["''", "'two words'", "[a, b]"])
def test_invalid_board_identity_is_named(tmp_path: Path, identity: str) -> None:
    body = "accounts:\n" + _with_identity("owner.business", identity)
    with pytest.raises(AccountFileError, match="owner.business: board_identity"):
        load_accounts(_write(tmp_path, body), ROLES, "dev")


def test_duplicate_board_identity_names_both_accounts(tmp_path: Path) -> None:
    body = (
        "accounts:\n"
        + _with_identity("owner.business", "same@example.test")
        + _with_identity("owner.product", "SAME@example.test")
    )
    with pytest.raises(AccountFileError) as raised:
        load_accounts(_write(tmp_path, body), ROLES, "dev")
    message = str(raised.value)
    assert "owner.business" in message and "owner.product" in message
    assert "board_identity" in message
