"""US8: a mapping that does not fit the board stops the sync, by name (T046; FR-004)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from adlc.engagement import store
from adlc.engagement.model import BoardType
from adlc.engagement.worker import BoardWorker
from tests.support.board import Rig
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness


def worker_for(rig: Rig) -> BoardWorker:
    engagement = SimpleNamespace(
        board=rig.board,
        mapping=rig.mapping,
        inbound=rig.sync,
        projector=rig.projector,
        engine=rig.h.app,
    )
    return BoardWorker(cast(Any, engagement))


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


def test_a_missing_field_stops_the_sync(rig: Rig, h: Harness) -> None:
    run_type = rig.mapping.item("run").type
    offered = rig.board._state.types[run_type]  # noqa: SLF001 - make the board lack one field
    rig.board._state.types[run_type] = BoardType(  # type: ignore[index]  # noqa: SLF001
        run_type, offered.states, offered.fields - {rig.mapping.decision_field}
    )
    walk_to(h, "T1")
    worker = worker_for(rig)
    worker.step()
    assert worker.status == "mapping_invalid"
    assert any(rig.mapping.decision_field in gap for gap in worker.gaps)
    with h.app.connect() as conn:
        assert store.sync_state(conn).last_poll_outcome == "mapping_invalid"
    assert rig.board.item_ids() == []  # nothing projected


def test_a_refused_token_is_reported(rig: Rig) -> None:
    worker = worker_for(rig)
    worker.engagement.board = rig.board.with_token_refused()
    assert not worker.check()
    assert worker.status == "degraded"


def test_a_fitting_board_syncs(rig: Rig, h: Harness) -> None:
    walk_to(h, "T1")
    worker = worker_for(rig)
    worker.step()
    assert worker.status == "ok" and worker.gaps == []
    assert rig.board.item_ids()
