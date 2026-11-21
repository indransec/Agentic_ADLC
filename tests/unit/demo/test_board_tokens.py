"""020 T010: the demo people's board tokens file (research R-06)."""

from __future__ import annotations

import logging
import stat
from pathlib import Path

import pytest

from adlc.demo.tokens import TokensFileError, ensure_tokens, read_tokens

USERS = ["product.owner@adlc.demo", "release.manager@adlc.demo"]


def test_created_when_missing_private_and_stable(tmp_path: Path) -> None:
    path = tmp_path / "secrets" / "board-tokens.yaml"
    first = ensure_tokens(path, USERS)
    assert set(first) == set(USERS)
    assert all(len(token) >= 40 for token in first.values())
    assert len(set(first.values())) == len(USERS)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert ensure_tokens(path, USERS) == first  # kept across resets
    assert read_tokens(path) == first


def test_a_new_user_gets_a_token_and_the_others_are_kept(tmp_path: Path) -> None:
    path = tmp_path / "board-tokens.yaml"
    first = ensure_tokens(path, USERS[:1])
    both = ensure_tokens(path, USERS)
    assert both[USERS[0]] == first[USERS[0]] and USERS[1] in both


def test_never_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    tokens = ensure_tokens(tmp_path / "t.yaml", USERS)
    assert not any(token in caplog.text for token in tokens.values())
    assert "t.yaml" not in repr(tokens.get("x"))


def test_unreadable_or_loose_files_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    ensure_tokens(path, USERS)
    path.chmod(0o644)
    with pytest.raises(TokensFileError, match="0600"):
        read_tokens(path)
    with pytest.raises(TokensFileError, match="no tokens file"):
        read_tokens(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("tokens: [1, 2]\n")
    bad.chmod(0o600)
    with pytest.raises(TokensFileError, match="user to token"):
        read_tokens(bad)
