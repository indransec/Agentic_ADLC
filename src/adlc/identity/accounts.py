"""Local account file loader (FR-018, FR-019, contracts/files.md).

Every problem is reported by account name. Credential hashes never appear in messages.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from adlc.identity.hashing import is_placeholder

ACCOUNT_NAME = re.compile(r"^[a-z][a-z0-9._-]{1,39}$")
FIELDS = frozenset({"account_name", "display_name", "roles", "credential_hash"})


class AccountFileError(ValueError):
    """The account file has one or more problems; the message lists them all."""


@dataclass(frozen=True)
class Account:
    account_name: str
    display_name: str
    roles: frozenset[str]
    credential_hash: str

    @property
    def can_sign_in(self) -> bool:
        return not is_placeholder(self.credential_hash)

    def __repr__(self) -> str:  # never show the hash
        return f"Account(account_name={self.account_name!r}, roles={sorted(self.roles)!r})"


def _problems_for(
    entry: dict[str, Any], role_ids: frozenset[str], env: str
) -> tuple[str, list[str]]:
    name = entry.get("account_name")
    label = name if isinstance(name, str) else "<no account_name>"
    problems: list[str] = []
    if not isinstance(name, str) or not ACCOUNT_NAME.match(name):
        problems.append(f"account_name {label!r} does not match {ACCOUNT_NAME.pattern}")
    unknown_keys = sorted(set(entry) - FIELDS)
    if unknown_keys:
        problems.append(f"unknown keys: {', '.join(unknown_keys)}")
    display = entry.get("display_name")
    if not isinstance(display, str) or not display.strip():
        problems.append("display_name is missing")
    roles = entry.get("roles")
    if not isinstance(roles, list) or not roles:
        problems.append("roles must be a non-empty list")
    else:
        for role in roles:
            if role not in role_ids:
                problems.append(f"unknown role {role}")
    credential = entry.get("credential_hash")
    if not isinstance(credential, str):
        problems.append("credential_hash is missing")
    elif env == "demo" and is_placeholder(credential):
        problems.append("credential_hash is a placeholder (run: adlc-account hash)")
    return label, problems


def load_accounts(
    path: Path, role_ids: frozenset[str], env: Literal["dev", "demo"] | str
) -> dict[str, Account]:
    try:
        data = YAML(typ="safe").load(path.read_text())
    except (OSError, YAMLError) as exc:
        raise AccountFileError(f"{path}: cannot read account file ({type(exc).__name__})") from None
    entries = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise AccountFileError(f"{path}: expected an 'accounts' list")

    problems: list[str] = []
    accounts: dict[str, Account] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(f"accounts[{index}]: not a mapping")
            continue
        label, entry_problems = _problems_for(entry, role_ids, env)
        if label in accounts:
            entry_problems.append(f"duplicate account_name {label}")
        problems.extend(f"{label}: {problem}" for problem in entry_problems)
        if not entry_problems:
            accounts[label] = Account(
                account_name=label,
                display_name=str(entry["display_name"]),
                roles=frozenset(entry["roles"]),
                credential_hash=str(entry["credential_hash"]),
            )
    if problems:
        raise AccountFileError(f"{path}:\n  " + "\n  ".join(problems))
    return accounts
