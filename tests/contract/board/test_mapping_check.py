"""US8: the real tracker mapping fits the simulator's seeded board (T046; FR-004)."""

from __future__ import annotations

import pytest

from adlc.engagement.mapping import TrackerMapping
from tests.contract.board.conftest import ROOT, Boards


@pytest.mark.board_contract
def test_the_mapping_fits_the_simulator(board: Boards) -> None:
    if board.kind != "ado":
        pytest.skip("checked against the real simulator only")
    mapping = TrackerMapping.load(ROOT / "adlc-specs" / "tracker_mapping.yaml")
    assert mapping.check_against(board.service.check()) == []
