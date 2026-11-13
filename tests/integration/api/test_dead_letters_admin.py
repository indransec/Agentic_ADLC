"""013 T017 (US5; FR-006; SC-005): dead letters show why and where they failed; the payload and
re-queue history are for the CoE role only; a re-queued event is delivered and recorded."""

from sqlalchemy import text

from tests.support.api import Api
from tests.support.orchestration import Harness

COE = "adlc_coe"  # ADLC_DEADLETTER_ROLE in the test settings


def _dead_letter(h: Harness) -> None:
    with h.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE events.outbox_event SET dead_lettered_at = now(), attempts = 5, "
                "last_error = 'route failed: subscriber unavailable' "
                "WHERE event_type = 'usecase.submitted'"
            )
        )


def test_dead_letter_details_and_history(h: Harness, api: Api) -> None:
    usecase = h.submit()
    _dead_letter(h)
    (dead,) = api.get(COE, "/dead-letters").json()
    assert dead["attempts"] == 5 and dead["last_error"].startswith("route failed")
    assert dead["usecase_id"] == usecase and dead["requeues"] == 0
    detail = api.get(COE, f"/dead-letters/{dead['event_id']}").json()
    assert detail["payload"] and detail["history"] == []
    assert api.get("sre", f"/dead-letters/{dead['event_id']}").status_code == 403
    assert api.get(COE, "/dead-letters/00000000-0000-0000-0000-000000000000").status_code == 404

    assert api.post(COE, f"/dead-letters/{dead['event_id']}/requeue").status_code == 204
    h.drain()  # the fault is gone: the event is delivered
    detail = api.get(COE, f"/dead-letters/{dead['event_id']}").json()
    assert detail["processed_at"] is not None
    assert [(e["action"], e["actor"]) for e in detail["history"]] == [("requeue", f"{COE}-person")]
    assert h.active(usecase, "T0") is not None
