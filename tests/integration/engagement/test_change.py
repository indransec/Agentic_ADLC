"""020 US2: a release's ITSM change request decided on the board (FR-008, FR-008a)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from adlc.engagement import store
from adlc.engagement.model import ItemWrite
from tests.support.board import Rig
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, person

APPROVER = "release_manager"  # the ITSM server's owner role (adlc-specs mcp_servers)


@pytest.fixture
def rig(h: Harness) -> Rig:
    return Rig(h)


def _raise_change(h: Harness, usecase: str, run_id: str, terminal: str) -> str:
    """A change request as the ITSM mock records it when an agent raises one (feature 012)."""
    body = {
        "summary": "Release it-triage 1.0 to production",
        "window_start": "2026-11-21T10:00:00+00:00",
        "window_end": "2026-11-21T12:00:00+00:00",
        "risk": "low",
        "plan": "canary then full",
        "state": "new",
    }
    with h.owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO enterprise_record (system, kind, record_id, version, usecase_id, "
                "run_id, terminal_id, body, at) VALUES ('servicenow', 'change', 'CHG-0001', 1, "
                ":u, :r, :t, :b, :n)"
            ),
            {"u": usecase, "r": run_id, "t": terminal, "b": json.dumps(body), "n": h.clock.now()},
        )
        # the run's next event marks the use case for delivery; stand in for it
        store.mark_dirty(conn, [usecase], h.clock.now())
    return "CHG-0001"


@pytest.fixture
def raised(rig: Rig, h: Harness) -> tuple[str, str, str]:
    usecase, run_id = walk_to(h, "T1")
    rig.cycle()
    change = _raise_change(h, usecase, run_id, "T1")
    rig.cycle()
    return usecase, run_id, change


def _fields(rig: Rig, change: str) -> dict[str, Any]:
    return dict(rig.board.get(rig.item("change", change)).fields)


def _decide(rig: Rig, role: str, change: str, value: str, comment: str = "ok") -> None:
    rig.as_role(role).update(
        rig.item("change", change),
        ItemWrite(set={rig.mapping.decision_field: value, rig.mapping.comment_field: comment}),
    )


def _record(h: Harness, change: str) -> dict[str, Any]:
    rows = h.sql(
        "SELECT body FROM enterprise_record WHERE record_id = :c ORDER BY version DESC", c=change
    )
    body = rows[0][0]
    return body if isinstance(body, dict) else json.loads(body)


def test_a_change_request_appears_under_its_run(rig: Rig, raised: tuple[str, str, str]) -> None:
    _, run_id, change = raised
    item = rig.board.get(rig.item("change", change))
    assert item.parent_id == rig.item("run", run_id)
    assert item.fields[rig.mapping.field("change", "state")] == rig.mapping.change_state("awaiting")
    assert APPROVER in str(item.fields[rig.mapping.field("change", "description")])


@pytest.mark.parametrize(
    ("value", "state"), [("approve_change", "approved"), ("reject_change", "rejected")]
)
def test_the_owner_role_decides_it_on_the_board(
    rig: Rig, h: Harness, raised: tuple[str, str, str], value: str, state: str
) -> None:
    _, _, change = raised
    _decide(rig, APPROVER, change, rig.mapping.value_for(value), "window agreed")
    rig.cycle()
    record = _record(h, change)
    assert record["state"] == state
    assert record["decided_by"] == person(APPROVER).account_name
    assert record["comment"] == "window agreed"
    assert record["source"]["board_item"] == rig.item("change", change)
    assert _fields(rig, change)[rig.mapping.field("change", "state")] == rig.mapping.change_state(
        state
    )
    assert _fields(rig, change).get(rig.mapping.decision_field) in (None, "")
    assert rig.outcomes()[-1] == ("accepted", None)
    commands = [
        r[0] for r in h.sql("SELECT command FROM inbound_outcome WHERE command IS NOT NULL")
    ]
    assert commands[-1] == (
        "decide_change:approve" if state == "approved" else "decide_change:reject"
    )


def test_another_role_is_refused(rig: Rig, h: Harness, raised: tuple[str, str, str]) -> None:
    _, _, change = raised
    _decide(rig, "sre", change, rig.mapping.value_for("approve_change"))
    rig.cycle()
    assert _record(h, change)["state"] == "new"
    assert rig.outcomes()[-1] == ("refused", "not_authorised")
    assert any("refused" in c for c in rig.comments("change", change))
    assert _fields(rig, change).get(rig.mapping.decision_field) in (None, "")


def test_a_second_decision_is_refused(rig: Rig, h: Harness, raised: tuple[str, str, str]) -> None:
    _, _, change = raised
    _decide(rig, APPROVER, change, rig.mapping.value_for("approve_change"))
    rig.cycle()
    _decide(rig, APPROVER, change, rig.mapping.value_for("reject_change"))
    rig.cycle()
    assert _record(h, change)["state"] == "approved"
    assert rig.outcomes()[-1] == ("refused", "stale")


def test_values_belong_to_their_kind(rig: Rig, h: Harness, raised: tuple[str, str, str]) -> None:
    _, run_id, change = raised
    _decide(rig, APPROVER, change, rig.mapping.value_for("pass"))
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "unknown_value")
    assert any(rig.mapping.value_for("approve_change") in c for c in rig.comments("change", change))
    rig.as_role("product_owner").update(
        rig.item("run", run_id),
        ItemWrite(set={rig.mapping.decision_field: rig.mapping.value_for("approve_change")}),
    )
    rig.cycle()
    assert rig.outcomes()[-1] == ("refused", "unknown_value")
    offered = [
        c.split("use one of:", 1)[1] for c in rig.comments("run", run_id) if "use one of" in c
    ]
    assert offered and not any(rig.mapping.value_for("approve_change") in o for o in offered)


def test_reconciliation_restores_a_drifted_change_item(
    rig: Rig, h: Harness, raised: tuple[str, str, str]
) -> None:
    _, _, change = raised
    state = rig.mapping.field("change", "state")
    rig.board.update(rig.item("change", change), ItemWrite(set={state: "Rejected"}))  # the service
    report = rig.reconciler().reconcile(person("adlc_coe"))
    assert any(d["object_id"] == change and d["field"] == state for d in report["differences"])
    assert _fields(rig, change)[state] == rig.mapping.change_state("awaiting")
