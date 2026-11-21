"""The board tables' SQL (T020; data-model.md)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DatabaseError

from adlc.engagement import store
from adlc.orchestration.outbox import RETRY_DELAYS
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person

NOW = datetime(2026, 11, 21, 10, 0, tzinfo=UTC)


def _usecase(h: Harness) -> str:
    return str(h.service.submit_usecase(person("business_owner"), "Store case", "x" * 250))


def test_links(h: Harness) -> None:
    usecase = _usecase(h)
    with h.app.begin() as conn:
        store.put_link(conn, "usecase", usecase, 11, "Epic", NOW)
        store.set_projection(conn, "usecase", usecase, "abc", 3, NOW)
        store.set_inbound_update(conn, 11, 4, NOW)
        store.set_inbound_update(conn, 11, 2, NOW)  # never moves back
    with h.app.connect() as conn:
        link = store.get_link(conn, "usecase", usecase)
        assert link == store.link_by_item(conn, 11)
        assert link is not None
        assert (link.projected_hash, link.last_written_rev, link.inbound_update_id) == ("abc", 3, 4)
        assert store.get_link(conn, "run", usecase) is None
    with pytest.raises(DatabaseError), h.app.begin() as conn:  # one item, one object
        store.put_link(conn, "run", "other", 11, "Feature", NOW)


def test_sync_state_and_watermark(h: Harness) -> None:
    with h.app.begin() as conn:
        assert store.sync_state(conn).watermark is None
        store.set_watermark(conn, "2026-11-21T10:00:00.000001Z")
        store.record_poll(conn, "board_unreachable", "x" * 3000, NOW)
        store.set_cursor(conn, {"run_activity_id": 5})
    with h.app.connect() as conn:
        state = store.sync_state(conn)
    assert state.watermark == "2026-11-21T10:00:00.000001Z"
    assert state.last_poll_outcome == "board_unreachable"
    assert state.last_error is not None and len(state.last_error) == 2000
    assert state.cursor == {"run_transition_id": 0, "run_activity_id": 5, "usecase_rowid": 0}


def test_changed_usecases_moves_the_cursor(h: Harness) -> None:
    usecase, _ = walk_to(h, "T1")
    with h.app.connect() as conn:
        found, cursor = store.changed_usecases(conn, {k: 0 for k in store.CURSOR_KEYS})
        assert usecase in found
        again, same = store.changed_usecases(conn, cursor)
    assert again == set() and same == cursor
    other = _usecase(h)  # no run yet: found by the use case cursor alone
    with h.app.connect() as conn:
        found, _ = store.changed_usecases(conn, cursor)
    assert found == {other}


def test_delivery_retries_then_dead_letters(h: Harness) -> None:
    usecase = _usecase(h)
    with h.app.begin() as conn:
        store.mark_dirty(conn, [usecase], NOW)
        store.mark_dirty(conn, [usecase], NOW + timedelta(minutes=1))  # keeps the first time
        assert store.due_deliveries(conn, NOW) == [usecase]
        dead = [
            store.delivery_failed(conn, usecase, "board down", NOW, RETRY_DELAYS)
            for _ in range(len(RETRY_DELAYS) + 1)
        ]
        assert dead == [False] * len(RETRY_DELAYS) + [True]
        assert store.due_deliveries(conn, NOW + timedelta(days=1)) == []
        summary = store.delivery_summary(conn)
        assert summary["dead_lettered"] == [usecase] and summary["pending"] == 0
        store.mark_dirty(conn, [usecase], NOW)  # still dead until requeued
        assert store.due_deliveries(conn, NOW + timedelta(days=1)) == []
        assert store.requeue(conn, usecase, "coe.lead", NOW)
        assert not store.requeue(conn, usecase, "coe.lead", NOW)
        assert store.due_deliveries(conn, NOW) == [usecase]
        store.delivered(conn, usecase, NOW)
        assert store.due_deliveries(conn, NOW + timedelta(days=1)) == []


def test_first_failure_waits_the_first_delay(h: Harness) -> None:
    usecase = _usecase(h)
    with h.app.begin() as conn:
        store.mark_dirty(conn, [usecase], NOW)
        store.delivery_failed(conn, usecase, "x", NOW, RETRY_DELAYS)
        assert store.due_deliveries(conn, NOW + RETRY_DELAYS[0] - timedelta(seconds=1)) == []
        assert store.due_deliveries(conn, NOW + RETRY_DELAYS[0]) == [usecase]


def test_claims_and_outcomes_once(h: Harness) -> None:
    change = store.Claim(
        7, 3, 2, "someone@board.test", "owner.business", "decide", "UC-0001/T1/run-1"
    )
    with h.app.begin() as conn:
        assert store.claim(conn, change, NOW)
        assert not store.claim(conn, change, NOW)
        assert store.unresolved_claims(conn) == [change]
        assert store.write_outcome(
            conn, 7, 3, "refused", NOW, reason_code="not_authorised", reason="no", reverted=True
        )
        assert not store.write_outcome(conn, 7, 3, "accepted", NOW)
        assert store.unresolved_claims(conn) == []
        counts = store.outcome_counts(conn)
    assert counts == {"refused_by_reason": {"not_authorised": 1}, "reverted": 1}
    with pytest.raises(DatabaseError), h.app.begin() as conn:
        conn.execute(text("DELETE FROM inbound_outcome"))


def test_activity_with_source(h: Harness) -> None:
    _, run_id = walk_to(h, "T1")
    h.service.decide(person("product_owner"), run_id, "pass", source={"board_item": 9, "update": 4})
    with h.app.connect() as conn:
        assert store.activity_with_source(conn, 9, 4)
        assert not store.activity_with_source(conn, 9, 5)
        assert not store.activity_with_source(conn, 19, 4)
    usecase = h.service.submit_usecase(
        person("business_owner"), "From board", "x" * 250, source={"board_item": 30, "update": 1}
    )
    assert usecase
    with h.app.connect() as conn:
        assert store.activity_with_source(conn, 30, 1)


def test_reconciliation_records(h: Harness) -> None:
    with h.app.begin() as conn:
        first = store.insert_reconciliation(
            conn, "coe.lead", NOW, NOW, "ok", 5, 1, [{"field": "x"}]
        )
        second = store.insert_reconciliation(conn, "coe.lead", NOW, NOW, "ok", 5, 0, [])
    with h.app.connect() as conn:
        assert store.reconciliation(conn)["id"] == second  # type: ignore[index]
        assert store.reconciliation(conn, first)["differences"] == [{"field": "x"}]  # type: ignore[index]
        assert store.reconciliation(conn, 999) is None


def test_migrated_database_has_the_board_tables(engine: Engine) -> None:
    """The plain migrated database has the board tables and the single sync-state row."""
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM board_sync_state")).scalar_one() == 1
