"""The dashboard's read-only views (feature 013, research R-01 to R-08, contracts/api-dashboard.md).

Everything comes from records the platform already writes: runs and their transitions, routing
events with causation, sign-offs, waivers, clarifications, run activity, agent attempts, model and
tool calls. Nothing is written here. Lanes come from the use case's pinned specs; no terminal or
use-case name is in code.
"""

import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from sqlalchemy import Connection, text

from adlc.api.errors import NotFound
from adlc.dashboard import kpis
from adlc.dashboard.journey import arrow_kind, terminal_order
from adlc.dashboard.timesplit import Transition, split
from adlc.inbox.rules import needed_sign_off_roles
from adlc.orchestration import durations, spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.engine import PostgresTerminalRun
from adlc.orchestration.states import RunState
from adlc.orchestration.store import RunRow

ACTIVITY_LIMIT, ACTIVITY_MAX = 200, 1000  # contracts/api-dashboard.md
DEFAULT_TIER = "medium"  # as the policy engine assumes before the tier is set
MAX_BARS = 20
TERMINAL_EVENT = re.compile(
    r"^[A-Z][0-9]+\."
)  # events a terminal raised  # bars per lane before the oldest collapse into one (research R-03)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class DashboardService:
    def __init__(self, runs: PostgresTerminalRun, time_scale: float = 1.0) -> None:
        self.runs, self.time_scale = runs, time_scale

    @property
    def engine(self) -> Any:
        return self.runs.engine

    def _spec(self, run: RunRow) -> Mapping[str, Any]:
        return self.runs.entry(run.terminal_id, run.spec_version).spec

    # -------------------------------------------------------------- shared record queries

    def _usecase(self, conn: Connection, usecase_id: str) -> Any:
        found = run_store.load_usecase(conn, usecase_id)
        if found is None:
            raise NotFound(f"use case {usecase_id}")
        return found

    @staticmethod
    def _transitions(conn: Connection, run_ids: list[str]) -> dict[str, list[Transition]]:
        found: dict[str, list[Transition]] = defaultdict(list)
        if not run_ids:
            return found
        rows = conn.execute(
            text(
                "SELECT run_id, to_state, at FROM run.run_transition WHERE run_id = ANY(:r) "
                "ORDER BY run_transition_id"
            ),
            {"r": run_ids},
        ).all()
        for run_id, state, at in rows:
            found[str(run_id)].append(Transition(str(state), at))
        return found

    @staticmethod
    def _events(conn: Connection, event_ids: list[Any]) -> dict[str, dict[str, Any]]:
        if not event_ids:
            return {}
        rows = conn.execute(
            text(
                "SELECT event_id, event_type, causation_run_id, payload FROM events.outbox_event "
                "WHERE event_id = ANY(:e)"
            ),
            {"e": event_ids},
        ).mappings()
        return {str(r["event_id"]): dict(r) for r in rows}

    @staticmethod
    def _sign_offs(conn: Connection, run_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        found: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if not run_ids:
            return found
        rows = conn.execute(
            text(
                "SELECT run_id, role, person, decision, comment, root_cause, fields, signed_at "
                "FROM run.sign_off WHERE run_id = ANY(:r) ORDER BY sign_off_id"
            ),
            {"r": run_ids},
        ).mappings()
        for r in rows:
            found[str(r["run_id"])].append(dict(r))
        return found

    @staticmethod
    def _waivers(conn: Connection, usecase_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                "SELECT w.waiver_id, w.run_id, w.status, w.expiry FROM run.waiver w JOIN "
                "run.terminal_run r USING (run_id) WHERE r.usecase_id = :u ORDER BY w.waiver_id"
            ),
            {"u": usecase_id},
        ).mappings()
        return [{**dict(r), "expiry": str(r["expiry"]) if r["expiry"] else None} for r in rows]

    def _open_round_role(self, conn: Connection, run_id: str) -> str | None:
        found = conn.execute(
            text(
                "SELECT c.addressed_role FROM run.clarification_round c LEFT JOIN "
                "run.clarification_answer a USING (clarification_id) WHERE c.run_id = :r "
                "AND a.clarification_id IS NULL ORDER BY c.asked_at DESC LIMIT 1"
            ),
            {"r": run_id},
        ).scalar()
        return None if found is None else str(found)

    # -------------------------------------------------------------- activity (US2)

    def activity(
        self,
        usecase_id: str | None = None,
        terminal_id: str | None = None,
        actor_type: str | None = None,
        step: str | None = None,
        limit: int = ACTIVITY_LIMIT,
    ) -> list[dict[str, Any]]:
        """Run activity newest first, filtered (research R-05; FR-003)."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT a.run_activity_id, a.run_id, r.usecase_id, r.terminal_id, a.step, "
                    "a.actor_type, a.actor_id, a.outcome, a.started_at, a.ended_at "
                    "FROM run.run_activity a JOIN run.terminal_run r USING (run_id) WHERE "
                    "(CAST(:u AS text) IS NULL OR r.usecase_id = :u) AND "
                    "(CAST(:t AS text) IS NULL OR r.terminal_id = :t) AND "
                    "(CAST(:a AS text) IS NULL OR a.actor_type = :a) AND "
                    "(CAST(:s AS text) IS NULL OR a.step = :s) "
                    "ORDER BY a.ended_at DESC, a.run_activity_id DESC LIMIT :n"
                ),
                {
                    "u": usecase_id,
                    "t": terminal_id,
                    "a": actor_type,
                    "s": step,
                    "n": max(1, min(int(limit), ACTIVITY_MAX)),
                },
            ).mappings()
            return [
                {
                    "at": _iso(r["ended_at"]),
                    "usecase_id": r["usecase_id"],
                    "run_id": r["run_id"],
                    "terminal_id": r["terminal_id"],
                    "actor_type": r["actor_type"],
                    "actor": r["actor_id"],
                    "step": r["step"],
                    "outcome": r["outcome"],
                    "seconds": (r["ended_at"] - r["started_at"]).total_seconds(),
                }
                for r in rows
            ]

    # -------------------------------------------------------------- run timeline (US4)

    def run_timeline(self, run_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            run = run_store.load_run(conn, run_id)
            if run is None:
                raise NotFound(f"run {run_id}")
            activity = [
                {
                    "at": _iso(r["started_at"]),
                    "step": r["step"],
                    "actor_type": r["actor_type"],
                    "actor": r["actor_id"],
                    "outcome": r["outcome"],
                    "seconds": (r["ended_at"] - r["started_at"]).total_seconds(),
                }
                for r in conn.execute(
                    text(
                        "SELECT step, actor_type, actor_id, outcome, started_at, ended_at FROM "
                        "run.run_activity WHERE run_id = :r ORDER BY started_at, run_activity_id"
                    ),
                    {"r": run_id},
                ).mappings()
            ]
            attempts = [
                dict(r)
                for r in conn.execute(
                    text(
                        "SELECT kind, attempt, agent_id, implementation, steps, tokens_in, "
                        "tokens_out, cost_usd FROM run.agent_attempt WHERE run_id = :r "
                        "ORDER BY agent_attempt_id"
                    ),
                    {"r": run_id},
                ).mappings()
            ]
            calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in conn.execute(
                text(
                    "SELECT agent_attempt_ref, provider, model, tokens_in, tokens_out, cost_usd, "
                    "latency_ms, outcome, called_at FROM run.model_call WHERE run_id = :r "
                    "ORDER BY model_call_id"
                ),
                {"r": run_id},
            ).mappings():
                calls[str(r["agent_attempt_ref"])].append(
                    {
                        "model": str(r["model"])
                        if "/" in str(r["model"])
                        else f"{r['provider']}/{r['model']}",
                        "tokens_in": r["tokens_in"],
                        "tokens_out": r["tokens_out"],
                        "cost_usd": float(r["cost_usd"]) if r["cost_usd"] is not None else None,
                        "latency_ms": float(r["latency_ms"]),
                        "outcome": r["outcome"],
                        "at": _iso(r["called_at"]),
                    }
                )
            tools: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for r in conn.execute(
                text(
                    "SELECT attempt, step, tool, outcome, reason, duration_ms, at FROM "
                    "tools.tool_call WHERE run_id = :r ORDER BY tool_call_id"
                ),
                {"r": run_id},
            ).mappings():
                tools[int(r["attempt"])].append(
                    {
                        "step": r["step"],
                        "tool": r["tool"],
                        "outcome": r["outcome"],
                        "reason": r["reason"],
                        "duration_ms": r["duration_ms"],
                        "at": _iso(r["at"]),
                    }
                )
        for a in attempts:
            a["cost_usd"] = float(a["cost_usd"]) if a["cost_usd"] is not None else None
            a["model_calls"] = calls.get(f"{run_id}/{a['kind']}/{a['attempt']}", [])
            a["tool_calls"] = tools.get(int(a["attempt"]), []) if a["kind"] == "build" else []
        return {"run_id": run_id, "activity": activity, "attempts": attempts}

    # -------------------------------------------------------------- KPIs (US3, US6)

    def records(self, conn: Connection, usecase_id: str) -> kpis.Records:
        """Everything the KPIs read for one use case (research R-05)."""
        usecase = self._usecase(conn, usecase_id)
        runs = run_store.runs_of_usecase(conn, usecase_id)
        ids = [r.run_id for r in runs]
        tier = usecase.risk_tier or DEFAULT_TIER
        facts = []
        for run in runs:
            spec = self._spec(run)
            policy = self.runs.registry.timeline(run.terminal_id, tier, run.spec_version)
            facts.append(
                kpis.RunFact(
                    run_id=run.run_id,
                    terminal_id=run.terminal_id,
                    run_number=run.run_number,
                    final_status=run.final_status,
                    opened_at=run.opened_at,
                    closed_at=run.closed_at,
                    recommendation=(run.recommendation or {}).get("status"),
                    expected_seconds=_seconds(policy.expected_duration) if policy else None,
                    blocking_controls=tuple(c.id for c in spec_view.controls(spec) if c.blocking),
                )
            )
        sign_offs = [
            kpis.SignOff(run_id, str(s["decision"]), s["root_cause"])
            for run_id, found in self._sign_offs(conn, ids).items()
            for s in found
        ]
        rounds = [
            kpis.Round(str(r[0]), str(r[1]), r[2], r[3])
            for r in conn.execute(
                text(
                    "SELECT c.run_id, c.addressed_role, c.asked_at, a.answered_at FROM "
                    "run.clarification_round c LEFT JOIN run.clarification_answer a "
                    "USING (clarification_id) WHERE c.run_id = ANY(:r) ORDER BY c.asked_at"
                ),
                {"r": ids},
            ).all()
        ]
        escalations = [
            (str(r[0]), r[1])
            for r in conn.execute(
                text(
                    "SELECT t.run_id, r.escalation_trigger FROM run.run_transition t JOIN "
                    "run.terminal_run r USING (run_id) WHERE t.run_id = ANY(:r) "
                    "AND t.to_state = 'escalated' ORDER BY t.run_transition_id"
                ),
                {"r": ids},
            ).all()
        ]
        versions = [
            kpis.ArtifactVersion(str(r[0]), str(r[1]), int(r[2]), str(r[3]))
            for r in conn.execute(
                text(
                    "SELECT run_id, artifact_id, version, producer_type FROM run.artifact_version "
                    "WHERE run_id = ANY(:r)"
                ),
                {"r": ids},
            ).all()
        ]
        decisions = [
            kpis.ControlDecision(str(r[0]), str(r[1]), int(r[2] or 1), bool(r[3]))
            for r in conn.execute(
                text(
                    "SELECT run_id, check_id, attempt, passed FROM run.policy_decision "
                    "WHERE run_id = ANY(:r) AND kind = 'evaluate' AND check_id LIKE 'CTL-%' "
                    "ORDER BY policy_decision_id"
                ),
                {"r": ids},
            ).all()
        ]
        closed = conn.execute(
            text("SELECT closed_at FROM run.usecase WHERE usecase_id = :u"), {"u": usecase_id}
        ).scalar()
        return kpis.Records(
            submitted_at=self._submitted(conn, usecase_id),
            closed_at=closed,
            now=self.runs.clock.now(),
            runs=facts,
            transitions=self._transitions(conn, ids),
            sign_offs=sign_offs,
            rounds=rounds,
            escalations=escalations,
            artifact_versions=versions,
            control_decisions=decisions,
        )

    @staticmethod
    def _submitted(conn: Connection, usecase_id: str) -> datetime:
        """When the lifecycle started (SA §12.3): the first run's opening, on the engine's clock
        like every other time here; the submission time before any run."""
        found = conn.execute(
            text(
                "SELECT coalesce(min(r.opened_at), u.created_at) FROM run.usecase u LEFT JOIN "
                "run.terminal_run r USING (usecase_id) WHERE u.usecase_id = :u "
                "GROUP BY u.created_at"
            ),
            {"u": usecase_id},
        ).scalar_one()
        return cast(datetime, found)

    def kpis(self, usecase_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            return {"kpis": kpis.compute(self.records(conn, usecase_id))}

    def portfolio(self, risk_tier: str | None = None, status: str | None = None) -> dict[str, Any]:
        with self.engine.connect() as conn:
            usecases = [
                str(u)
                for u in conn.execute(
                    text(
                        "SELECT usecase_id FROM run.usecase WHERE "
                        "(CAST(:t AS text) IS NULL OR risk_tier = :t) AND "
                        "(CAST(:s AS text) IS NULL OR status = :s) ORDER BY usecase_id"
                    ),
                    {"t": risk_tier, "s": status},
                ).scalars()
            ]
            found = [self.records(conn, u) for u in usecases]
        return {"usecases": len(usecases), "kpis": kpis.pool(found, self.runs.clock.now())}

    # -------------------------------------------------------------- journey (US1)

    def owner(self, conn: Connection, run: RunRow) -> str | None:
        """Who an open run waits for (research R-03, checklist CHK002)."""
        spec = self._spec(run)
        state = run.state
        if state == RunState.CLOSED:
            return None
        if state == RunState.BUILDING:
            agent = (spec_view.body(spec).get("actors") or {}).get("agent") or {}
            return f"agent {agent.get('id', '')}".strip()
        if state in (RunState.CHECKING, RunState.REVIEWING):
            return "reviewer"
        if state == RunState.AWAITING_CLARIFICATION:
            role = self._open_round_role(conn, run.run_id)
            return f"role {role}" if role else "clarification"
        if state == RunState.AWAITING_SIGN_OFF:
            needed = sorted(needed_sign_off_roles(self.runs.context(conn, run)))
            return "sign-off: " + ", ".join(needed) if needed else "sign-off"
        if state in (RunState.ESCALATED, RunState.BLOCKED):
            return "accountable: " + ", ".join(sorted(spec_view.accountable_roles(spec)))
        return "orchestrator"

    def journey(self, usecase_id: str) -> dict[str, Any]:
        now = self.runs.clock.now()
        with self.engine.connect() as conn:
            usecase = self._usecase(conn, usecase_id)
            runs = run_store.runs_of_usecase(conn, usecase_id)
            ids = [r.run_id for r in runs]
            transitions = self._transitions(conn, ids)
            events = self._events(conn, [r.trigger_event_id for r in runs if r.trigger_event_id])
            sign_offs = self._sign_offs(conn, ids)
            waivers = self._waivers(conn, usecase_id)
            pinned = run_store.pins(conn, usecase_id)
            owners = {r.run_id: self.owner(conn, r) for r in runs}
        bars: dict[str, dict[str, Any]] = {
            r.run_id: {
                "run_id": r.run_id,
                "terminal_id": r.terminal_id,
                "run_number": r.run_number,
                "state": str(r.state),
                "final_status": r.final_status,
                "mode": r.mode,
                "opened_at": _iso(r.opened_at),
                "closed_at": _iso(r.closed_at),
                "seconds": ((r.closed_at or now) - r.opened_at).total_seconds(),
                "owner": owners[r.run_id],
                "time_split": split(transitions.get(r.run_id, []), now=now),
            }
            for r in runs
        }
        lanes = []
        for terminal in sorted(pinned, key=terminal_order):
            entry = self.runs.entry(terminal, pinned[terminal])
            name = str((spec_view.body(entry.spec).get("metadata") or {}).get("name") or terminal)
            in_lane = sorted(
                (b for b in bars.values() if b["terminal_id"] == terminal),
                key=lambda b: b["run_number"],
            )
            lanes.append({"terminal_id": terminal, "name": name, "runs": _collapse(in_lane)})
        by_run = {r.run_id: r for r in runs}
        arrows = []
        unlinked = []  # spec edge case: an event from a terminal whose run is unknown
        for run in runs:
            event = events.get(str(run.trigger_event_id)) if run.trigger_event_id else None
            if event is None:
                continue
            source = _source_run(event, run, runs, by_run)
            if source is None:
                if TERMINAL_EVENT.match(str(event["event_type"])):
                    unlinked.append({"run_id": run.run_id, "event_type": event["event_type"]})
                continue
            kind = arrow_kind(str(event["event_type"]), source.terminal_id, run.terminal_id)
            decided = [s for s in sign_offs.get(source.run_id, []) if s["decision"] != "pass"]
            every = sign_offs.get(source.run_id) or []
            last = decided[-1] if decided else (every[-1] if every else None)
            arrows.append(
                {
                    "from_run": source.run_id,
                    "to_run": run.run_id,
                    "kind": kind,
                    "event_type": event["event_type"],
                    "cause": _cause(kind, event, last, waivers, source.run_id),
                    "actor": (last or {}).get("person")
                    or (event.get("payload") or {}).get("raised_by"),
                    "at": _iso(run.opened_at),
                }
            )
        panel = {
            "escalations": [
                {"run_id": r.run_id, "terminal_id": r.terminal_id, "trigger": r.escalation_trigger}
                for r in runs
                if r.escalation_trigger
            ],
            "exceptions": [w for w in waivers if w["status"] == "approved"],
            "unlinked": unlinked,
        }
        return {
            "usecase": {
                "usecase_id": usecase.usecase_id,
                "name": usecase.name,
                "risk_tier": usecase.risk_tier,
                "status": usecase.status,
            },
            "lanes": lanes,
            "arrows": arrows,
            "panel": panel,
            "time_scale": self.time_scale,
        }


def _seconds(value: str | None) -> float | None:
    found = durations.parse_optional(value) if value else None
    return found.total_seconds() if found is not None else None


def _source_run(
    event: Mapping[str, Any], target: RunRow, runs: list[RunRow], by_run: Mapping[str, RunRow]
) -> RunRow | None:
    """The run an arrow starts from: the event's causation run; for an operational event raised
    after its terminal's run closed (a continuous terminal between periods), the run named in the
    payload, else that terminal's latest run opened before the target."""
    payload = dict(event.get("payload") or {})
    for ref in (
        event.get("causation_run_id"),
        payload.get("source_run_id"),
        payload.get("proposed_by"),
    ):
        if ref and str(ref) in by_run:
            return by_run[str(ref)]
    terminal = str(event.get("event_type") or "").partition(".")[0]
    earlier = [
        r
        for r in runs
        if r.terminal_id == terminal
        and r.run_id != target.run_id
        and r.opened_at <= target.opened_at
    ]
    return max(earlier, key=lambda r: r.opened_at) if earlier else None


def _collapse(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Beyond ``MAX_BARS`` the oldest bars collapse into one bar (continuous terminals)."""
    if len(bars) <= MAX_BARS:
        return bars
    older, kept = bars[: len(bars) - MAX_BARS + 1], bars[len(bars) - MAX_BARS + 1 :]
    earlier = {
        "run_id": None,
        "terminal_id": older[0]["terminal_id"],
        "run_number": older[0]["run_number"],
        "state": "collapsed",
        "final_status": f"{len(older)} earlier runs",
        "opened_at": older[0]["opened_at"],
        "closed_at": older[-1]["closed_at"],
        "seconds": sum(b["seconds"] for b in older),
        "owner": None,
        "time_split": {},
        "collapsed": len(older),
    }
    return [earlier, *kept]


def _cause(
    kind: str,
    event: Mapping[str, Any],
    sign_off: Mapping[str, Any] | None,
    waivers: list[dict[str, Any]],
    source_run: str,
) -> dict[str, Any]:
    payload = dict(event.get("payload") or {})
    if kind == "event":
        return {
            k: payload[k]
            for k in ("monitor_id", "signal", "measured", "proposed_event_id", "confirmed_by")
            if k in payload
        }
    if kind == "exception":
        found = [w for w in waivers if w["run_id"] == source_run]
        return {
            "waiver_id": found[-1]["waiver_id"] if found else None,
            "expiry": found[-1]["expiry"] if found else None,
            "comment": (sign_off or {}).get("comment"),
        }
    if sign_off is None:
        return {}
    return {
        k: v
        for k, v in (
            ("root_cause", sign_off.get("root_cause")),
            ("comment", sign_off.get("comment")),
            ("decision", sign_off.get("decision")),
        )
        if v
    }
