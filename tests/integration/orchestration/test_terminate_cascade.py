"""T039: terminate ends the lifecycle (FR-018c; US2/AC6)."""

from adlc.orchestration import ids, store
from adlc.orchestration.service import Actor
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person


def test_terminate_closes_every_active_run(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    h.service.raise_operational_event(Actor.system("monitor"), usecase, "drift", {})
    h.drain()
    t9 = h.active(usecase, "T9")
    h.service.decide(person("business_owner"), run_id, "terminate", comment="no business case")
    h.drain()
    assert h.run(run_id).final_status == "terminate"
    assert h.run(t9.run_id).final_status == "terminate"
    reasons = h.sql(
        "SELECT reason FROM run.run_transition WHERE run_id = :r AND to_state = 'closed'",
        r=t9.run_id,
    )
    assert reasons[0][0] == "lifecycle terminated"
    assert (
        h.sql("SELECT count(*) FROM run.timer WHERE fired_at IS NULL AND cancelled_at IS NULL")[0][
            0
        ]
        == 0
    )
    assert h.service.get_usecase(usecase).status == "terminated"
    # only the deciding run emits an outcome event; cascade closes write ledger records only
    assert [
        r[0]
        for r in h.sql(
            "SELECT event_type FROM events.outbox_event WHERE event_type LIKE '%.terminate'"
        )
    ] == ["T1.terminate"]
    assert (
        h.sql("SELECT count(*) FROM ledger.ledger_record WHERE run_id = :r", r=t9.run_id)[0][0] == 1
    )


def test_later_events_are_ignored(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T1")
    h.service.decide(person("business_owner"), run_id, "terminate", comment="stop")
    h.drain()
    with h.app.begin() as conn:
        store.insert_event(
            conn,
            event_id=ids.uuid7(),
            event_type="T0.pass",
            usecase_id=usecase,
            correlation_id=ids.correlation_id(usecase),
            causation_run_id=None,
            payload={},
            now=h.clock.now(),
        )
    h.drain()
    assert all(r.state == "closed" for r in h.runs(usecase))
    assert h.sql("SELECT count(*) FROM events.outbox_event WHERE processed_at IS NULL")[0][0] == 0


def test_terminate_with_retirement_subscribers(h: Harness) -> None:
    usecase, run_id = walk_to(h, "T8")
    h.service.decide(person("business_owner"), run_id, "terminate", comment="retire the agent")
    h.drain()
    t9 = h.active(usecase, "T9")
    assert (t9.mode, t9.trigger_event_type) == ("retire", "T8.terminate")
    assert h.service.get_usecase(usecase).status == "active"
    h.service.decide(
        person("business_owner"), t9.run_id, "terminate", comment="retirement complete"
    )
    h.drain()
    assert h.service.get_usecase(usecase).status == "terminated"


def test_terminate_records_notify_roles(h: Harness) -> None:
    """US2/AC6 (T081): the outcome's notify roles are recorded on the terminate event."""
    usecase = h.submit()
    t0 = h.active(usecase, "T0").run_id
    h.service.decide(person("business_owner"), t0, "terminate", comment="out of scope")
    payload = h.sql("SELECT payload FROM events.outbox_event WHERE event_type = 'T0.terminate'")
    assert payload[0][0]["notify"] == ["adlc_coe"]
