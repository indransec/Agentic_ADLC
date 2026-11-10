"""T072: the role file the API reads must match the registered roles catalogue (FR-025)."""

import logging
from pathlib import Path

import pytest
from sqlalchemy import Engine

from adlc.api.startup import RoleCatalogueMismatch, check_role_catalogue
from adlc.spec_toolkit.register import register

ROOT = Path(__file__).resolve().parents[3]
ROLES = ROOT / "adlc-specs" / "shared" / "roles.yaml"


def test_matching_file_passes(owner_engine: Engine, app_engine: Engine) -> None:
    register(ROOT / "adlc-specs", owner_engine)
    check_role_catalogue(ROLES, app_engine)


def test_mismatch_stops_startup(owner_engine: Engine, app_engine: Engine, tmp_path: Path) -> None:
    register(ROOT / "adlc-specs", owner_engine)
    changed = tmp_path / "roles.yaml"
    changed.write_text(ROLES.read_text().replace("Owns build quality", "Owns build quality!"))
    with pytest.raises(RoleCatalogueMismatch, match=r"roles 1\.0\.0"):
        check_role_catalogue(changed, app_engine)


def test_unregistered_catalogue_warns(app_engine: Engine, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    check_role_catalogue(ROLES, app_engine)
    assert any("not registered" in r.getMessage() for r in caplog.records)
