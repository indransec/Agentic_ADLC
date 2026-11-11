"""The read side for people (007): use cases, journeys, the inbox and run details.

Everything is derived from the tables of features 003, 005 and 006; nothing is stored here
(research R-03). Who may act comes from ``adlc.inbox.rules``, which the operations use too.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from adlc.agents.cost import terminal_cost, usecase_cost
from adlc.api.errors import NotFound
from adlc.inbox.rules import Actor
from adlc.ledger.service import LedgerService
from adlc.orchestration import spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.engine import PostgresTerminalRun
from adlc.orchestration.store import RunRow


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
        self, runs: PostgresTerminalRun, ledger: LedgerService, deadletter_role: str | None
    ) -> None:
        self.runs = runs
        self.ledger = ledger
        self.deadletter_role = deadletter_role

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


def first(values: Mapping[str, Any]) -> Any:
    return next(iter(values.values()), None)
