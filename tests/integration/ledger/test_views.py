"""T030: read views per run and per use case (US5; FR-020 to FR-022)."""

from datetime import timedelta
from pathlib import Path
from typing import Any

from adlc.ledger import views
from adlc.orchestration.interfaces import Clarification, Recommendation
from adlc.orchestration.stubs import StubAgent, StubReviewer
from tests.support.ledger import ledger_service
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness, harness, person
from tests.support.pg import PlatformDatabase

ASK = Clarification(("Which channels are in scope?",))
REVIEW = Recommendation(
    "pass", {"traceable": 2, "complete": 3}, ("traceable: KPI-02 has no source", "overall sound")
)


def test_lifecycle_views(orch_template: PlatformDatabase, tmp_path: Path) -> None:
    """One clarification at T2, one rework of T1; the timeline, checks and summary show them."""
    agent = StubAgent({"T2": {1: ASK}})
    reviewer = StubReviewer({"T1": {1: REVIEW}})
    with harness(orch_template, agent=agent, reviewer=reviewer) as h:
        ledger = ledger_service(h, tmp_path / "files")
        # Open runs count up to the database's now(), so keep the fake clock in the past.
        h.clock.current -= timedelta(hours=2)
        usecase, t1 = walk_to(h, "T1")
        h.clock.advance(timedelta(hours=1))  # an hour waiting for sign-off
        h.pass_run(t1)
        t2 = h.active(usecase, "T2").run_id
        clar = h.sql("SELECT clarification_id FROM run.clarification_round")[0][0]
        h.service.answer_clarification(person("engineering_lead"), clar, ["web"])
        h.drain()
        h.service.decide(
            person("security_officer"),
            t2,
            "rework",
            comment="c",
            root_cause="requirement",
            reason="r",
        )
        h.drain()

        view = ledger.run_view(t1)
        steps = [s["step"] for s in view["timeline"]]
        order = [steps.index(s) for s in ("route", "prerequisites", "build", "controls", "review")]
        assert order == sorted(order)
        assert steps[-1] in ("sign_off", "close")
        assert all(
            s["duration_seconds"] is not None and s["duration_seconds"] >= 0
            for s in view["timeline"]
        )
        checks = view["checks"]
        controls = [c for c in checks if c["check_id"].startswith("CTL-")]
        others = [c for c in checks if not c["check_id"].startswith("CTL-")]
        assert controls and {(c["attempt"], c["recheck"]) for c in controls} == {(1, False)}
        assert others and {(c["attempt"], c["recheck"]) for c in others} == {(None, False)}
        assert all(c["reason"] for c in checks)
        assert any(c["check_id"].startswith("CTL-T1") for c in checks)
        assert [(c["item_id"], c["score"], c["finding"]) for c in view["checklist"]] == [
            ("traceable", 2, "KPI-02 has no source"),
            ("complete", 3, None),
            ("general", None, "overall sound"),
        ]
        assert {c["attempt"] for c in view["checklist"]} == {1}
        assert {v["artifact_id"] for v in view["artifact_versions"]} >= {"kpis"}
        assert view["ledger_record"]["ledger_key"].endswith("/T1/run-1")
        assert "content_json" not in view["ledger_record"]

        summary = {row["terminal_id"]: row for row in ledger.usecase_summary(usecase)}
        assert summary["T1"]["runs"] == 2 and summary["T1"]["reworks"] == 1
        assert summary["T1"]["waiting_seconds"] >= 3600
        assert summary["T2"]["clarification_rounds"] == 1
        assert summary["T2"]["escalations"] == 0
        assert summary["T0"]["automatic_seconds"] >= 0


def test_checklist_rows_per_review(orch_template: PlatformDatabase) -> None:
    """A blocked first attempt is retried; each review writes its rows once."""
    agent = StubAgent({"T1": {1: {"kpis": {"baseline": "n/a"}}}})
    with harness(orch_template, agent=agent) as h:
        usecase, t1 = walk_to(h, "T1")
        rows = h.sql(
            "SELECT attempt, count(*) FROM run.checklist_result WHERE run_id = :r GROUP BY attempt",
            r=t1,
        )
        assert [tuple(r) for r in rows] == [(2, len(h.reviewer.contexts[-1].checklist_items))]
        checks = h.sql(
            "SELECT max(n) FROM (SELECT count(*) AS n FROM run.policy_decision "
            "WHERE run_id = :r AND check_id LIKE 'CTL-%' GROUP BY check_id) x",
            r=t1,
        )
        assert checks[0][0] == 2  # controls ran for both attempts
        attempts = {
            (c["attempt"], c["recheck"])
            for c in ledger_views(h, t1)
            if c["check_id"].startswith("CTL-")
        }
        assert attempts == {(1, False), (2, False)}


def test_a_recheck_after_an_edit_keeps_the_attempt(h: Harness, tmp_path: Path) -> None:
    usecase, t1 = walk_to(h, "T1")
    ledger = ledger_service(h, tmp_path / "files")
    rows = [dict(r) for r in h.run(t1).artifacts["kpis"]]
    rows[0]["target"] = 6
    ledger.edit_artifact(person("product_owner"), t1, "kpis", rows)
    h.drain()
    controls = [c for c in ledger.run_view(t1)["checks"] if c["check_id"].startswith("CTL-")]
    assert {(c["attempt"], c["recheck"]) for c in controls} == {(1, False), (1, True)}
    assert len([c for c in controls if c["recheck"]]) == len(controls) // 2


def test_open_run_counts_to_now(orch_template: PlatformDatabase) -> None:
    with harness(orch_template) as h:
        usecase, t1 = walk_to(h, "T1")
        first = {r["terminal_id"]: r for r in ledger_rows(h, usecase)}["T1"]["waiting_seconds"]
        h.sql("SELECT pg_sleep(0.2)")
        later = {r["terminal_id"]: r for r in ledger_rows(h, usecase)}["T1"]["waiting_seconds"]
        assert later > first


def ledger_rows(h: Harness, usecase: str) -> list[dict[str, Any]]:
    with h.app.connect() as conn:
        return views.usecase_summary(conn, usecase)


def ledger_views(h: Harness, run_id: str) -> list[dict[str, Any]]:
    with h.app.connect() as conn:
        return views.run_checks(conn, run_id)
