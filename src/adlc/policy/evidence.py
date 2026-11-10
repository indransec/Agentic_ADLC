"""Evidence providers (research R-04; contracts/evidence.md).

A provider answers per source with ``Evidence`` or ``NOT_AVAILABLE``. ``CompositeEvidenceProvider``
prefers real evidence and marks synthetic evidence, so decisions that read it are labelled
(FR-025).
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from sqlalchemy import Connection, Engine

from adlc.orchestration import durations, spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.interfaces import Clock, EvalContext
from adlc.orchestration.store import RunRow
from adlc.policy import store as policy_store
from adlc.policy.directory import Directory, UnavailableDirectory
from adlc.policy.values import NOT_AVAILABLE, _NotAvailable
from adlc.spec_toolkit.registry import SpecRegistry


@dataclass(frozen=True)
class Evidence:
    value: Any
    source: str
    synthetic: bool = False


Answer = Evidence | _NotAvailable


class EvidenceProvider(Protocol):
    def get(self, source: str, context: EvalContext) -> Answer: ...


class InMemoryEvidenceProvider:
    """Fixed values per source (tests, and the synthetic provider's core)."""

    def __init__(self, sources: Mapping[str, Any], *, synthetic: bool = False) -> None:
        self.sources = dict(sources)
        self.synthetic = synthetic

    def get(self, source: str, context: EvalContext) -> Answer:
        if source not in self.sources:
            return NOT_AVAILABLE
        return Evidence(self.sources[source], source, self.synthetic)


class CompositeEvidenceProvider:
    def __init__(self, real: EvidenceProvider, synthetic: EvidenceProvider | None = None) -> None:
        self.real = real
        self.synthetic = synthetic

    def get(self, source: str, context: EvalContext) -> Answer:
        answer = self.real.get(source, context)
        if isinstance(answer, Evidence) or self.synthetic is None:
            return answer
        fallback = self.synthetic.get(source, context)
        if isinstance(fallback, Evidence):
            return Evidence(fallback.value, fallback.source, synthetic=True)
        return NOT_AVAILABLE


# ---------------------------------------------------------- SQL provider (feature 003 records)


TERMINAL = re.compile(r"^[A-Z][0-9]+$")
DEFAULT_TIER = "medium"
SIGNED_STATUSES = ("pass", "exception")
ParameterSource = Callable[[EvalContext], Answer]


class SqlEvidenceProvider:
    """Real evidence from the feature 003 records (FR-007 to FR-011)."""

    def __init__(
        self,
        engine: Engine,
        registry: SpecRegistry,
        clock: Clock,
        *,
        directory: Directory | None = None,
        parameters: ParameterSource | None = None,
    ) -> None:
        self.engine = engine
        self.registry = registry
        self.clock = clock
        self.directory = directory or UnavailableDirectory()
        self.parameters = parameters

    def get(self, source: str, context: EvalContext) -> Answer:
        variables = context.variables or {}
        if source in variables:
            return Evidence(variables[source], "caller")
        if source == "param":
            return NOT_AVAILABLE if self.parameters is None else self.parameters(context)
        if source == "directory":
            names = self.directory.names()
            return NOT_AVAILABLE if names is None else Evidence(sorted(names), "directory")
        if context.usecase_id is None:
            return NOT_AVAILABLE
        with self.engine.connect() as conn:
            value = self._read(conn, source, context)
        return NOT_AVAILABLE if value is NOT_AVAILABLE else Evidence(value, source)

    # -------------------------------------------------------------- sources

    def _read(self, conn: Connection, source: str, ctx: EvalContext) -> Any:
        usecase_id = str(ctx.usecase_id)
        if TERMINAL.match(source):
            return self._terminal(conn, usecase_id, source, ctx, depth=0)
        run = run_store.load_run(conn, ctx.run_id) if ctx.run_id else None
        usecase = run_store.load_usecase(conn, usecase_id)
        if usecase is None:
            return NOT_AVAILABLE
        tier = usecase.risk_tier or DEFAULT_TIER
        if source == "intake":
            return {
                "free_text": usecase.intake_text,
                "business_owner": usecase.submitted_by,
                "title": usecase.name,
            }
        if source == "waivers":
            return policy_store.approved_waivers(conn, usecase_id)
        if run is None:
            return NOT_AVAILABLE
        if source == "run":
            return {
                "rework_count": run.rework_count,
                "age": self.clock.now() - run.opened_at,
                "now": self.clock.now(),
                "usecase_id": run.usecase_id,
                "run_version": f"run-{run.run_number}",
                "risk_tier": tier,
                "mode": run.mode,
            }
        if source == "trigger":
            return _trigger(run)
        spec = self._spec(run)
        if source == "timeline":
            policy = self.registry.timeline(run.terminal_id, tier, run.spec_version)
            if policy is None:
                return NOT_AVAILABLE
            return {
                k: (durations.parse_optional(v) or v) if isinstance(v, str) else v
                for k, v in asdict(policy).items()
                if v is not None
            }
        if source == "tier":
            tiering = (spec_view.body(spec).get("controls") or {}).get("tiering") or {}
            value = tiering.get(tier) if isinstance(tiering, Mapping) else None
            return dict(value) if isinstance(value, Mapping) else {}
        return NOT_AVAILABLE

    def _spec(self, run: RunRow) -> Mapping[str, Any]:
        entry = self.registry.entry(run.terminal_id, run.spec_version)
        return entry.spec if entry is not None else {}

    def _terminal(
        self, conn: Connection, usecase_id: str, terminal_id: str, ctx: EvalContext, depth: int
    ) -> Any:
        own = terminal_id == ctx.terminal_id and ctx.run_id is not None
        run_id = (
            ctx.run_id if own else policy_store.latest_closed_run_id(conn, usecase_id, terminal_id)
        )
        run = run_store.load_run(conn, run_id) if run_id else None
        if run is None:
            return NOT_AVAILABLE
        sign_offs = [s for s in run_store.sign_offs(conn, run.run_id) if s["decision"] == "pass"]
        waivers = [
            w["waiver_id"]
            for w in policy_store.approved_waivers(conn, usecase_id)
            if w["run_id"] == run.run_id
        ]
        record: dict[str, Any] = {
            # Emitted values first: an emitted name that is an artifact is only a reference to
            # it, so the artifact itself must win (FR-008).
            **({} if own else policy_store.emitted_values(conn, run.run_id)),
            **run.artifacts,
            "status": run.final_status if run.final_status else "open",
            "signed_by": [s["person"] for s in sign_offs],
            "signed_roles": [s["role"] for s in sign_offs],
            "run_version": f"run-{run.run_number}",
            "waivers": waivers,
        }
        if run.closed_at is not None:
            record["closed_at"] = run.closed_at
        bound = self._bound_to(conn, usecase_id, run, ctx, depth)
        if bound is not None:
            record["bound_to"] = bound
        return record

    def _bound_to(
        self, conn: Connection, usecase_id: str, run: RunRow, ctx: EvalContext, depth: int
    ) -> Any:
        """The spec's ``ledger.bound_to`` reference resolved in this use case (FR-008)."""
        ledger = (spec_view.body(self._spec(run)).get("evidence") or {}).get("ledger") or {}
        reference = ledger.get("bound_to") if isinstance(ledger, Mapping) else None
        if not isinstance(reference, str) or depth > 2:
            return None
        root, *path = reference.split(".")
        if not TERMINAL.match(root):
            return None
        value = self._terminal(conn, usecase_id, root, ctx, depth + 1)
        for member in path:
            if isinstance(value, list):
                value = value[0] if value and isinstance(value[0], Mapping) else None
            if not isinstance(value, Mapping) or member not in value:
                return None
            value = value[member]
        return value


def _trigger(run: RunRow) -> dict[str, Any]:
    context = run.trigger_context or {}
    operational = context.get("operational_event")
    out: dict[str, Any] = {}
    if run.trigger_event_id is not None:
        out["event_id"] = str(run.trigger_event_id)
    if isinstance(operational, Mapping):
        if operational.get("severity") is not None:
            out["severity"] = operational["severity"]
        out["evidence"] = dict(operational)
    elif context.get("ledger_key"):
        out["evidence"] = context["ledger_key"]
    return out
