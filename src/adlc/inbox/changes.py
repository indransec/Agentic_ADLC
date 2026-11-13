"""Change requests decided in the inbox (feature 012, FR-012, research R-05,
contracts/api-changes.md).

An agent raises a change in the ITSM mock (feature 010); a person in the role that owns the ITSM
server in the MCP registry (spec content) approves or rejects it here. The decision is a new
version of the change record (append-only), with who decided, when and why. Runs whose controls
wait for that decision then re-run them (research R-11).
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Engine, bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from adlc.api.errors import NotFound
from adlc.orchestration.interfaces import Clock
from adlc.orchestration.service import Actor, NotAuthorised, OrchestratorService
from adlc.orchestration.states import InvalidTransition
from adlc.spec_toolkit.registry import SpecRegistry

SYSTEM, KIND = "servicenow", "change"  # the ITSM system and record kind of feature 010's mocks
WAITING = "new"
DECISIONS = {True: "approved", False: "rejected"}


def approver_role(registry: Mapping[str, Any] | None) -> str | None:
    """The owner role of the ITSM server in the MCP registry, or None."""
    for server in (registry or {}).get("mcp_servers") or []:
        if server.get("id") == SYSTEM and server.get("owner_role"):
            return str(server["owner_role"])
    return None


class ChangeService:
    def __init__(
        self,
        engine: Engine,
        registry: SpecRegistry,
        orchestration: OrchestratorService,
        clock: Clock,
    ) -> None:
        self.engine, self.registry, self.orchestration, self.clock = (
            engine,
            registry,
            orchestration,
            clock,
        )

    def approver(self) -> str | None:
        """The role that decides changes (the ITSM server's owner in the MCP registry)."""
        return self._role()

    def _role(self) -> str | None:
        entry = self.registry.catalogue("mcp_servers")
        return approver_role(entry.content if entry else None)

    def _may_decide(self, actor: Actor) -> bool:
        role = self._role()
        return actor.kind == "human" and role is not None and role in actor.roles

    def _current(self, record_id: str | None = None) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT ON (record_id) record_id, version, usecase_id, run_id, "
                    "terminal_id, body, at FROM tools.enterprise_record WHERE system = :s "
                    "AND kind = :k AND (CAST(:r AS text) IS NULL OR record_id = :r) "
                    "ORDER BY record_id, version DESC"
                ),
                {"s": SYSTEM, "k": KIND, "r": record_id},
            ).mappings()
            return [
                {
                    **dict(r["body"]),
                    "change_id": r["record_id"],
                    "record_version": r["version"],
                    "usecase_id": r["usecase_id"],
                    "run_id": r["run_id"],
                    "terminal_id": r["terminal_id"],
                    "at": r["at"].isoformat(),
                }
                for r in rows
            ]

    def waiting(self, actor: Actor) -> list[dict[str, Any]]:
        """Changes awaiting a decision, for the approver role (empty for anyone else)."""
        if not self._may_decide(actor):
            return []
        found = [c for c in self._current() if c.get("state") == WAITING]
        return sorted(found, key=lambda c: int(str(c["change_id"]).rpartition("-")[2] or 0))

    def decide(
        self, actor: Actor, change_id: str, approve: bool, comment: str | None
    ) -> dict[str, Any]:
        if not self._may_decide(actor):
            raise NotAuthorised(f"changes are decided by {self._role() or 'nobody configured'}")
        found = self._current(change_id)
        if not found:
            raise NotFound(f"change {change_id}")
        current = found[0]
        if current.get("state") != WAITING:
            raise InvalidTransition(f"{change_id} is already {current.get('state')}")
        meta = ("change_id", "record_version", "usecase_id", "run_id", "terminal_id", "at")
        body = {k: v for k, v in current.items() if k not in meta}
        body.update(
            state=DECISIONS[approve],
            decided_by=actor.account_name,
            decided_at=self.clock.now().isoformat(),
            comment=(comment or "")[:2000],
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO tools.enterprise_record (system, kind, record_id, version, "
                        "usecase_id, run_id, terminal_id, body, at) VALUES (:s, :k, :r, :v, :u, "
                        ":run, :t, :b, now())"
                    ).bindparams(bindparam("b", type_=JSONB)),
                    {
                        "s": SYSTEM,
                        "k": KIND,
                        "r": change_id,
                        "v": int(current["record_version"]) + 1,
                        "u": current["usecase_id"],
                        "run": current["run_id"],
                        "t": current["terminal_id"],
                        "b": body,
                    },
                )
        except IntegrityError:  # decided concurrently
            raise InvalidTransition(f"{change_id} was decided meanwhile") from None
        # runs whose controls wait for this decision re-run them (research R-11)
        self.orchestration.awaited_action_done(actor, str(current["usecase_id"]))
        return self._current(change_id)[0]
