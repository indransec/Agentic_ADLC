"""Lifecycle events an agent proposes, confirmed or dismissed by a person (feature 012, FR-007,
research R-02, contracts/api-changes.md).

Monitors raise events deterministically. An agent that sees a reason for a lifecycle event
(drift, cost overrun, a KPI shortfall) writes it as a row with status ``proposed`` in its events
table (any artifact with the columns ``event_id``, ``event_type`` and ``status``). A person in an
accountable role of that terminal confirms it, which raises the operational event, or dismisses
it. Either is recorded on the run's activity (step ``sign_off``); a row is decided once.
"""

import re
from typing import Any

from sqlalchemy import text

from adlc.api.errors import NotFound
from adlc.orchestration import spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.engine import PostgresTerminalRun
from adlc.orchestration.service import Actor, NotAuthorised, OrchestratorService
from adlc.orchestration.states import InvalidTransition
from adlc.orchestration.store import RunRow

EVENT_COLUMNS = frozenset({"event_id", "event_type", "status"})
PROPOSED = "proposed"
OUTCOMES = {True: "event_confirmed", False: "event_dismissed"}
QUALIFIED = re.compile(r"^[A-Z][0-9]+\.event\.([a-z][a-z0-9_]*)$")


def event_name(event_type: str) -> str:
    """``drift`` from ``drift`` or ``<terminal>.event.drift``."""
    matched = QUALIFIED.match(event_type.strip())
    return matched.group(1) if matched else event_type.strip()


class ProposedEventService:
    def __init__(self, runs: PostgresTerminalRun, orchestration: OrchestratorService) -> None:
        self.runs, self.orchestration = runs, orchestration

    def _spec(self, run: RunRow) -> Any:
        return self.runs.entry(run.terminal_id, run.spec_version).spec

    def _tables(self, run: RunRow) -> list[str]:
        return [
            a.id
            for a in spec_view.artifacts(self._spec(run))
            if set(a.columns) >= EVENT_COLUMNS and isinstance(run.artifacts.get(a.id), list)
        ]

    def _decided(self, conn: Any, run_id: str) -> set[str]:
        rows = conn.execute(
            text(
                "SELECT detail -> 'event_confirmation' ->> 'event_id' FROM run.run_activity "
                "WHERE run_id = :r AND outcome IN ('event_confirmed', 'event_dismissed')"
            ),
            {"r": run_id},
        ).scalars()
        return {str(r) for r in rows if r}

    def _proposals(self, conn: Any, run: RunRow) -> list[dict[str, Any]]:
        decided = self._decided(conn, run.run_id)
        return [
            {
                **{k: row.get(k) for k in ("event_id", "event_type", "raised_at", "routed_to")},
                "run_id": run.run_id,
                "usecase_id": run.usecase_id,
                "terminal_id": run.terminal_id,
            }
            for table in self._tables(run)
            for row in run.artifacts[table]
            if str(row.get("status", "")).strip().lower() == PROPOSED
            and str(row.get("event_id")) not in decided
        ]

    def waiting(self, actor: Actor) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        with self.runs.engine.connect() as conn:
            usecases = conn.execute(
                text("SELECT usecase_id FROM run.usecase WHERE status = 'active'")
            ).scalars()
            for usecase in list(usecases):
                for run in run_store.runs_of_usecase(conn, str(usecase)):
                    if actor.roles & spec_view.accountable_roles(self._spec(run)):
                        found += self._proposals(conn, run)
        return found

    def decide(
        self, actor: Actor, run_id: str, event_id: str, confirm: bool, comment: str | None
    ) -> dict[str, Any]:
        if actor.kind != "human":
            raise NotAuthorised("a person confirms or dismisses a proposed event")
        with self.runs.engine.begin() as conn:
            run = run_store.load_run(conn, run_id)
            if run is None:
                raise NotFound(f"run {run_id}")
            roles = spec_view.accountable_roles(self._spec(run))
            if not actor.roles & roles:
                raise NotAuthorised(f"proposed events are decided by {sorted(roles)}")
            if event_id in self._decided(conn, run_id):
                raise InvalidTransition(f"{event_id} is already decided")
            proposal = next(
                (p for p in self._proposals(conn, run) if p["event_id"] == event_id), None
            )
            if proposal is None:
                raise NotFound(f"proposed event {event_id} in {run_id}")
            now = self.runs.clock.now()
            decision = {
                "event_id": event_id,
                "event_type": proposal["event_type"],
                "confirmed": confirm,
                "by": actor.account_name,
                "comment": (comment or "")[:2000],
            }
            run_store.insert_activity(
                conn,
                run_id,
                "sign_off",
                "human",
                actor.account_name,
                now,
                now,
                OUTCOMES[confirm],
                {"event_confirmation": decision},
            )
        if confirm:
            raised = self.orchestration.raise_operational_event(
                Actor.system("proposal"),
                run.usecase_id,
                event_name(str(proposal["event_type"])),
                {
                    "proposed_by": run_id,
                    "proposed_event_id": event_id,
                    "confirmed_by": actor.account_name,
                },
            )
            decision["raised_event_id"] = str(raised)
        return decision
