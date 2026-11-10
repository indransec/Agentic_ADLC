"""T034: a full T0→T9 lifecycle with stub agents and scripted approvals (SC-001, SC-007)."""

from tests.support.orchestration import Harness

LIFECYCLE = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]


def test_t0_to_t9(h: Harness) -> None:
    usecase = h.submit()
    for terminal in LIFECYCLE:
        run = h.active(usecase, terminal)
        assert run.state == "awaiting_sign_off", (terminal, run.state)
        fields = {"risk_tier": "medium"} if terminal == "T0" else {}
        h.pass_run(run.run_id, fields)
        assert h.run(run.run_id).final_status == "pass"
    # T8 passes into "continue"; T9 opens on an operational event (D-7 covers it). Here the
    # lifecycle has walked every terminal once, with one ledger record per closed run.
    closed = [r for r in h.runs(usecase) if r.state == "closed"]
    assert [r.terminal_id for r in closed] == LIFECYCLE
    chain = h.sql(
        "SELECT ledger_key, content_hash, previous_record_hash FROM ledger.ledger_record "
        "WHERE usecase_id = :u ORDER BY ledger_record_id",
        u=usecase,
    )
    assert [row[0] for row in chain] == [r.run_id for r in closed]
    assert chain[0][2] is None
    assert all(chain[i][2] == chain[i - 1][1] for i in range(1, len(chain)))
    events = {row[0] for row in h.sql("SELECT event_type FROM events.outbox_event")}
    assert {f"{t}.pass" for t in LIFECYCLE} <= events
    assert h.service.get_usecase(usecase).risk_tier == "medium"
