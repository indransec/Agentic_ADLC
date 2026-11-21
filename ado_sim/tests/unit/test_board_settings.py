"""017 T007: the seed's board settings and the service account flag (FR-005; research R-08)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from ruamel.yaml import YAML

from ado_sim.db import Database
from ado_sim.process import board_settings, identity_by_name, is_service
from ado_sim.seed import SeedError, parse_seed
from tests.conftest import SEED, SERVICE


def _raw() -> dict[str, Any]:
    data: dict[str, Any] = YAML(typ="safe").load(SEED.read_text())
    return data


def test_the_demo_seed_has_a_board_and_a_service_account() -> None:
    seed = parse_seed(_raw())
    assert seed.board is not None
    assert seed.board.type == "Epic"
    assert seed.board.card_fields == ("Custom.AdlcSubStage",)
    assert seed.board.collapsed_states == ("Closed", "Removed")
    assert seed.board.refresh_seconds == 5
    assert [i.unique_name for i in seed.identities if i.service] == [SERVICE]


def test_a_seed_without_a_board_is_valid() -> None:
    raw = _raw()
    del raw["board"]
    assert parse_seed(raw).board is None


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"type": "Saga"}, "board.type"),
        ({"card_fields": ["Custom.Missing"]}, "board.card_fields"),
        ({"collapsed_states": ["Nowhere"]}, "board.collapsed_states"),
        ({"refresh": "1s"}, "board.refresh"),
        ({"refresh": "61s"}, "board.refresh"),
        ({"refresh": "5m"}, "board.refresh"),
        ({"columns": 3}, "unknown key"),
    ],
)
def test_board_refusals_name_the_key(change: dict[str, Any], named: str) -> None:
    raw = _raw()
    raw["board"] = {**copy.deepcopy(raw["board"]), **change}
    with pytest.raises(SeedError, match=named):
        parse_seed(raw)


def test_at_most_one_service_account() -> None:
    raw = _raw()
    raw["identities"][1]["service"] = True
    with pytest.raises(SeedError, match="service"):
        parse_seed(raw)


def test_loaded_settings_and_flag(db: Database) -> None:
    with db.read() as conn:
        settings = board_settings(conn)
        service = identity_by_name(conn, SERVICE)
        person = identity_by_name(conn, "product.owner@adlc.demo")
        assert service is not None and person is not None
        assert is_service(conn, service) and not is_service(conn, person)
    assert settings is not None and settings.type == "Epic" and settings.refresh_seconds == 5
