"""The read side for people (007): use cases, journeys, the inbox and run details.

Everything is derived from the tables of features 003, 005 and 006; nothing is stored here
(research R-03). Who may act comes from ``adlc.inbox.rules``, which the operations use too.
"""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from adlc.agents.cost import run_cost, terminal_cost, usecase_cost
from adlc.agents.prompts import SpecFileError, SqlSpecTexts
from adlc.api.errors import NotFound
from adlc.inbox import rules
from adlc.inbox.forms import build_form
from adlc.inbox.rules import Actor
from adlc.ledger import store as ledger_store
from adlc.ledger.service import LedgerService
from adlc.orchestration import spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.engine import PostgresTerminalRun
from adlc.orchestration.states import RunState
from adlc.orchestration.store import RunRow

FAR_FUTURE = datetime.max.isoformat()


def run_summary(run: RunRow) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "usecase_id": run.usecase_id,
        "terminal_id": run.terminal_id,
        "run_number": run.run_number,
        "state": str(run.state),
        "final_status": run.final_status,
        "version": run.version,
        "controls_pending": run.controls_pending,
        "opened_at": run.opened_at,
        "closed_at": run.closed_at,
        "due_at": run.due_at,
    }


class InboxService:
    def __init__(
        self,
        runs: PostgresTerminalRun,
        ledger: LedgerService,
        deadletter_role: str | None,
        spec_dir: Path,
    ) -> None:
        self.runs = runs
        self.ledger = ledger
        self.deadletter_role = deadletter_role
        self.texts = SqlSpecTexts(runs.engine, spec_dir)

    # -------------------------------------------------------------- use cases

    def _roles_of_run(self, run: RunRow) -> frozenset[str]:
        spec = self.runs.entry(run.terminal_id, run.spec_version).spec
        return frozenset(r.role for r in spec_view.human_roles(spec))

    def usecases(self, actor: Actor, mine: bool) -> list[dict[str, Any]]:
        with self.runs.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT u.usecase_id, u.name, u.submitted_by, u.risk_tier, u.status, "
                    "u.created_at AS submitted_at, count(r.run_id) FILTER "
                    "(WHERE r.state <> 'closed') AS open_runs FROM run.usecase u "
                    "LEFT JOIN run.terminal_run r USING (usecase_id) "
                    "GROUP BY u.usecase_id ORDER BY u.created_at DESC, u.usecase_id DESC"
                )
            ).mappings()
            found = [dict(r) for r in rows]
            if not mine:
                return found
            result = []
            for usecase in found:
                if usecase["submitted_by"] == actor.account_name:
                    result.append(usecase)
                    continue
                runs = run_store.runs_of_usecase(conn, usecase["usecase_id"])
                if any(actor.roles & self._roles_of_run(run) for run in runs):
                    result.append(usecase)
            return result

    def journey(self, usecase_id: str) -> dict[str, Any]:
        with self.runs.engine.connect() as conn:
            usecase = run_store.load_usecase(conn, usecase_id)
            if usecase is None:
                raise NotFound(f"no use case {usecase_id}")
            runs = run_store.runs_of_usecase(conn, usecase_id)
        engine = self.runs.engine
        terminals = sorted({r.terminal_id for r in runs})
        return {
            "usecase": {
                "usecase_id": usecase.usecase_id,
                "name": usecase.name,
                "intake_text": usecase.intake_text,
                "submitted_by": usecase.submitted_by,
                "risk_tier": usecase.risk_tier,
                "status": usecase.status,
            },
            "runs": [run_summary(r) for r in runs],
            "summary": self.ledger.usecase_summary(usecase_id),
            "cost": {
                "total": usecase_cost(engine, usecase_id),
                "terminals": {t: terminal_cost(engine, usecase_id, t) for t in terminals},
            },
        }

    # -------------------------------------------------------------- inbox

    def items(self, actor: Actor) -> list[dict[str, Any]]:
        """Everything waiting for this person (FR-006), soonest due first (research R-11)."""
        with self.runs.engine.connect() as conn:
            found = self._sign_off_items(conn, actor)
            found += self.request_items(conn, actor)
        return sorted(
            found,
            key=lambda i: (
                str(i["due_at"]) if i["due_at"] is not None else FAR_FUTURE,
                str(i["arrived_at"]),
            ),
        )

    def request_items(self, conn: Connection, actor: Actor) -> list[dict[str, Any]]:
        """Clarifications, escalations, waivers and dead letters (US4; research R-03)."""
        return (
            self._clarification_items(conn, actor)
            + self._escalation_items(conn, actor)
            + self._waiver_items(conn, actor)
            + self._blocked_items(conn, actor)
            + self._dead_letter_items(conn, actor)
        )

    def _clarification_items(self, conn: Connection, actor: Actor) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                "SELECT c.clarification_id, c.run_id, c.addressed_role, c.asked_at "
                "FROM run.clarification_round c LEFT JOIN run.clarification_answer a "
                "USING (clarification_id) WHERE a.clarification_id IS NULL ORDER BY c.asked_at"
            )
        ).mappings()
        items = []
        for row in rows:
            if not rules.can_answer(actor, row["addressed_role"]):
                continue
            run = run_store.load_run(conn, str(row["run_id"]))
            if run is None:
                continue
            items.append(
                _item(
                    "clarification",
                    str(row["clarification_id"]),
                    run,
                    row["addressed_role"],
                    f"Answer questions on {run.terminal_id} run {run.run_number}",
                    row["asked_at"],
                )
            )
        return items

    def _escalation_items(self, conn: Connection, actor: Actor) -> list[dict[str, Any]]:
        items = []
        for run in self._waiting(conn, RunState.ESCALATED.value):
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            roles = sorted(actor.roles & rules.accountable(spec))
            if not roles:
                continue
            items.append(
                _item(
                    "escalation",
                    run.run_id,
                    run,
                    roles[0],
                    f"Complete escalated {run.terminal_id} run {run.run_number}",
                    self._entered(conn, run.run_id, RunState.ESCALATED.value),
                )
            )
        return items

    def _waiver_items(self, conn: Connection, actor: Actor) -> list[dict[str, Any]]:
        ids = conn.execute(
            text(
                "SELECT w.waiver_id FROM run.waiver w JOIN run.terminal_run r "
                "ON r.pending_waiver_id = w.waiver_id WHERE w.status = 'proposed' "
                "ORDER BY w.proposed_at"
            )
        ).scalars()
        items = []
        for waiver_id in ids:
            waiver = run_store.load_waiver(conn, str(waiver_id))
            run = run_store.load_run(conn, str(waiver["run_id"])) if waiver else None
            if waiver is None or run is None:
                continue
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            if not rules.can_decide_waiver(actor, spec, str(waiver["proposed_by"])):
                continue
            role = sorted(actor.roles & rules.waiver_approvers(spec))[0]
            proposed = conn.execute(
                text("SELECT proposed_at FROM run.waiver WHERE waiver_id = :w"), {"w": waiver_id}
            ).scalar()
            items.append(
                _item(
                    "waiver",
                    str(waiver_id),
                    run,
                    role,
                    f"Decide waiver {waiver_id} on {run.terminal_id}",
                    proposed,
                )
            )
        return items

    def _blocked_items(self, conn: Connection, actor: Actor) -> list[dict[str, Any]]:
        """Runs held by an unmet prerequisite, for the accountable owner (change request
        2026-11-11): they can supply the evidence or terminate the run."""
        items = []
        for run in self._waiting(conn, RunState.BLOCKED.value):
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            roles = sorted(actor.roles & rules.accountable(spec))
            if not roles:
                continue
            items.append(
                _item(
                    "blocked",
                    run.run_id,
                    run,
                    roles[0],
                    f"Blocked {run.terminal_id} run {run.run_number}",
                    self._entered(conn, run.run_id, RunState.BLOCKED.value),
                )
            )
        return items

    def _prerequisites(
        self, conn: Connection, run_id: str, spec: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        """Each declared prerequisite with its latest result and reason from the policy decision
        log (feature 004); nothing is re-evaluated here."""
        declared = spec_view.prerequisite_entries(spec)
        latest: dict[str, Mapping[str, Any]] = {}
        rows = conn.execute(
            text(
                "SELECT check_id, passed, reason, synthetic FROM run.policy_decision "
                "WHERE run_id = :r AND check_id = ANY(:ids) "
                "ORDER BY decided_at, policy_decision_id"
            ),
            {"r": run_id, "ids": [p["id"] for p in declared]},
        ).mappings()
        for row in rows:
            latest[str(row["check_id"])] = dict(row)
        return [
            {
                **p,
                "passed": latest[p["id"]]["passed"] if p["id"] in latest else None,
                "reason": latest[p["id"]]["reason"] if p["id"] in latest else None,
                "synthetic": latest[p["id"]]["synthetic"] if p["id"] in latest else None,
            }
            for p in declared
        ]

    def _dead_letter_items(self, conn: Connection, actor: Actor) -> list[dict[str, Any]]:
        if not rules.is_coe(actor, self.deadletter_role):
            return []
        return [
            {
                "kind": "dead_letter",
                "id": str(row["event_id"]),
                "usecase_id": row["usecase_id"],
                "terminal_id": None,
                "run_id": None,
                "role": self.deadletter_role,
                "title": f"Dead-lettered event {row['event_type']}",
                "arrived_at": row["dead_lettered_at"],
                "due_at": None,
                "controls_pending": False,
            }
            for row in run_store.dead_letters(conn)
        ]

    # -------------------------------------------------------------- lookups for the routes

    def clarification_exists(self, clarification_id: str) -> bool:
        with self.runs.engine.connect() as conn:
            return run_store.load_clarification(conn, clarification_id) is not None

    def waiver_exists(self, waiver_id: str) -> bool:
        with self.runs.engine.connect() as conn:
            return run_store.load_waiver(conn, waiver_id) is not None

    def _waiting(self, conn: Connection, state: str) -> list[RunRow]:
        ids = conn.execute(
            text("SELECT run_id FROM run.terminal_run WHERE state = :s ORDER BY opened_at"),
            {"s": state},
        ).scalars()
        return [r for r in (run_store.load_run(conn, str(i)) for i in ids) if r is not None]

    def _entered(self, conn: Connection, run_id: str, state: str) -> Any:
        return conn.execute(
            text("SELECT max(at) FROM run.run_transition WHERE run_id = :r AND to_state = :s"),
            {"r": run_id, "s": state},
        ).scalar()

    def _sign_off_items(self, conn: Connection, actor: Actor) -> list[dict[str, Any]]:
        items = []
        for run in self._waiting(conn, RunState.AWAITING_SIGN_OFF.value):
            ctx = self.runs.context(conn, run)
            role = rules.sign_off_role(actor, ctx)
            if role is None:
                continue
            items.append(
                _item(
                    "sign_off",
                    run.run_id,
                    run,
                    role,
                    f"Sign off {run.terminal_id} run {run.run_number}",
                    self._entered(conn, run.run_id, RunState.AWAITING_SIGN_OFF.value),
                )
            )
        return items

    # -------------------------------------------------------------- run detail

    def detail(self, run_id: str, actor: Actor) -> dict[str, Any]:
        """Everything SA 8.2 asks for on one page (FR-008), plus the decision form (FR-009)."""
        with self.runs.engine.connect() as conn:
            run = run_store.load_run(conn, run_id)
            if run is None:
                raise NotFound(f"no run {run_id}")
            entry = self.runs.entry(run.terminal_id, run.spec_version)
            spec = entry.spec
            ctx = self.runs.context(conn, run)
            sign_offs = run_store.sign_offs(conn, run_id)
            clarifications = run_store.clarifications(conn, run_id)
            prior = self._prior_rework(conn, run)
            prerequisites = self._prerequisites(conn, run_id, spec)
            pins = run_store.pins(conn, run.usecase_id)
            versions = {v["artifact_id"]: v for v in ledger_store.latest_versions(conn, run_id)}
            attachments = {
                aid: ledger_store.attachments(conn, run_id, aid, int(v["version"]))
                for aid, v in versions.items()
            }
            waiver = (
                run_store.load_waiver(conn, run.pending_waiver_id)
                if run.pending_waiver_id
                else None
            )
        cutoff = run.approvals_after_sign_off_id or 0
        recommendation = dict(run.recommendation or {})
        if recommendation:
            recommendation["items"] = self._checklist(spec, recommendation)
        view = self.ledger.run_view(run_id)
        now = self.runs.clock.now()
        return {
            "run": run_summary(run),
            "spec": {"terminal_id": run.terminal_id, "version": entry.version},
            "artifacts": [
                {
                    "id": a.id,
                    "columns": list(a.columns),
                    "condition": a.condition,
                    "rows": run.artifacts.get(a.id),
                    "version": _version(versions.get(a.id)),
                    "attachments": attachments.get(a.id, []),
                }
                for a in spec_view.artifacts(spec)
            ],
            "prerequisites": prerequisites,
            "control_results": list(run.control_results),
            "recommendation": recommendation or None,
            "prior_rework": prior,
            "clarifications": clarifications,
            "approvals": [
                {k: s[k] for k in ("person", "role", "signed_at")}
                for s in sign_offs
                if s["decision"] == "pass" and int(s["sign_off_id"]) > cutoff
            ],
            "decisions": sign_offs,
            "waiver": waiver,
            "timer": {
                "due_at": run.due_at,
                "overdue": run.due_at is not None and now > run.due_at and run.closed_at is None,
            },
            "cost": run_cost(self.runs.engine, run_id),
            "timeline": view["timeline"],
            "checks": view["checks"],
            "checklist_results": view["checklist"],
            "ledger_record": view["ledger_record"],
            "form": build_form(
                spec=spec,
                run=run,
                ctx=ctx,
                actor=actor,
                registry=self.runs.registry,
                destination_kind=self.runs.destination_kind,
                catalogue_root_causes=self._root_causes(),
                pinned_terminals=pins.keys(),
            ),
        }

    def _prior_rework(self, conn: Connection, run: RunRow) -> list[dict[str, Any]]:
        """Earlier runs of this terminal in this use case that closed as rework, newest first."""
        found = []
        for earlier in reversed(run_store.runs_of_usecase(conn, run.usecase_id)):
            if (
                earlier.terminal_id != run.terminal_id
                or earlier.run_id == run.run_id
                or earlier.final_status != "rework"
            ):
                continue
            for s in run_store.sign_offs(conn, earlier.run_id):
                if s["decision"] == "rework":
                    found.append(
                        {
                            "run_id": earlier.run_id,
                            "person": s["person"],
                            "signed_at": s["signed_at"],
                            "comment": s["comment"],
                            "root_cause": s["root_cause"],
                        }
                    )
        return found

    def _checklist(
        self, spec: Mapping[str, Any], recommendation: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        ref = (spec_view.body(spec).get("controls") or {}).get("checklist") or {}
        try:
            texts = {
                i.id: i.text
                for i in self.texts.checklist(str(ref.get("ref")), str(ref.get("version")))
            }
        except SpecFileError:
            texts = {}
        scores = recommendation.get("checklist_scores") or {}
        return [
            {"id": item, "text": texts.get(item, ""), "score": scores.get(item)}
            for item in spec_view.checklist_items(spec)
        ]

    def attachment(self, run_id: str, content_hash: str) -> tuple[str, str] | None:
        """(file name, media type) of an attachment recorded on this run, else None (R-06)."""
        with self.runs.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT file_name, media_type FROM run.artifact_attachment "
                    "WHERE run_id = :r AND content_hash = :h ORDER BY version DESC LIMIT 1"
                ),
                {"r": run_id, "h": content_hash},
            ).first()
        return None if row is None else (str(row[0]), str(row[1]))

    def _root_causes(self) -> tuple[str, ...]:
        catalogue = self.runs.registry.catalogue("root_causes")
        return tuple(
            str(i["id"]) for i in (catalogue.content if catalogue else {}).get("root_causes", [])
        )


def _item(
    kind: str, item_id: str, run: RunRow, role: str, title: str, arrived_at: Any
) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": item_id,
        "usecase_id": run.usecase_id,
        "terminal_id": run.terminal_id,
        "run_id": run.run_id,
        "role": role,
        "title": title,
        "arrived_at": arrived_at,
        "due_at": run.due_at,
        "controls_pending": run.controls_pending,
    }


def _version(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "version": row["version"],
        "producer_type": row["producer_type"],
        "producer_id": row["producer_id"],
        "schema_valid": row["schema_valid"],
        "created_at": row["created_at"],
    }
