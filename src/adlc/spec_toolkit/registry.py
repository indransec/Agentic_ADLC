"""Read interface over registered specs (contracts/spec-registry-interface.md; FR-024, FR-025).

Platform modules read spec data only through ``SpecRegistry``. ``SqlSpecRegistry`` reads the
``spec`` schema with the application identity; ``InMemorySpecRegistry`` is built from validated
files through the same projection code, so both give identical answers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import Engine, text

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.loader import SpecBundle
from adlc.spec_toolkit.projections import (
    ChangeClass,
    EventRoute,
    OutcomeRoute,
    Projection,
    Timeline,
    project,
)
from adlc.spec_toolkit.rules.single_spec import spec


@dataclass(frozen=True)
class TerminalRef:
    terminal_id: str
    version: str


@dataclass(frozen=True)
class RouteTarget:
    kind: str  # terminal | event | special | template | disabled | terminating
    destination: str
    alternatives: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    recheck_at: tuple[str, ...] = ()
    set_by: tuple[str, ...] = ()
    notify: tuple[str, ...] = ()
    condition: str | None = None


@dataclass(frozen=True)
class EventRouteTarget:
    kind: str
    destination: str
    immediate: tuple[str, ...] = ()
    then_destination: str | None = None
    notify: tuple[str, ...] = ()
    condition: str | None = None


@dataclass(frozen=True)
class ChangeClassRoute:
    reentry_terminal: str
    path: tuple[str, ...] = ()
    retrospective: tuple[str, ...] = ()
    within: str | None = None
    alternative: str | None = None


@dataclass(frozen=True)
class TimelinePolicy:
    risk_tier: str
    expected_duration: str | None
    continuous: bool
    reminder_after: str
    escalate_after: str | None
    escalate_at_window_end: bool
    max_rework_cycles: int
    clarification_sla: str
    max_clarification_rounds: int
    max_auto_retries: int | None
    retirement_duration: str | None


@dataclass(frozen=True)
class RegistryEntry:
    terminal_id: str
    version: str
    status: str
    content_hash: str
    spec: dict[str, Any] = field(compare=False, hash=False)
    registered_at: datetime | None = None


@dataclass(frozen=True)
class CatalogueEntry:
    name: str
    version: str
    content: dict[str, Any] = field(compare=False, hash=False)


class SpecRegistry(Protocol):
    def terminals_opened_by(self, event_type: str) -> tuple[TerminalRef, ...]: ...

    def outcome_route(
        self,
        terminal_id: str,
        status: str,
        root_cause: str | None = None,
        version: str | None = None,
    ) -> RouteTarget | None: ...

    def event_route(
        self, terminal_id: str, event_type: str, version: str | None = None
    ) -> EventRouteTarget | None: ...

    def change_class_route(
        self, terminal_id: str, change_class: str, version: str | None = None
    ) -> ChangeClassRoute | None: ...

    def timeline(
        self, terminal_id: str, risk_tier: str, version: str | None = None
    ) -> TimelinePolicy | None: ...

    def entry(self, terminal_id: str, version: str | None = None) -> RegistryEntry | None: ...

    def catalogue(self, name: str) -> CatalogueEntry | None: ...


# ------------------------------------------------------------------ conversions


def _route(r: OutcomeRoute) -> RouteTarget:
    return RouteTarget(
        r.destination_kind,
        r.destination,
        r.alternatives,
        r.requires,
        r.recheck_at,
        r.set_by,
        r.notify,
        r.condition,
    )


def _event(e: EventRoute) -> EventRouteTarget:
    return EventRouteTarget(
        e.destination_kind, e.destination, e.immediate, e.then_destination, e.notify, e.condition
    )


def _change(c: ChangeClass) -> ChangeClassRoute:
    return ChangeClassRoute(c.reentry_terminal, c.path, c.retrospective, c.within, c.alternative)


def _timeline(t: Timeline) -> TimelinePolicy:
    return TimelinePolicy(
        t.risk_tier,
        t.expected_duration,
        t.continuous,
        t.reminder_after,
        t.escalate_after,
        t.escalate_at_window_end,
        t.max_rework_cycles,
        t.clarification_sla,
        t.max_clarification_rounds,
        t.max_auto_retries,
        t.retirement_duration,
    )


def _pick_route(
    rows: list[OutcomeRoute], status: str, root_cause: str | None
) -> RouteTarget | None:
    candidates = [r for r in rows if r.outcome_status == status]
    if status == "rework" and root_cause is not None:
        for r in candidates:
            if r.root_cause == root_cause:
                return _route(r)
    for r in candidates:
        if r.root_cause is None:
            return _route(r)
    return None


# ------------------------------------------------------------------ in memory


class InMemorySpecRegistry:
    """Registry over validated files (tests, and feature 003 before a database exists)."""

    def __init__(
        self,
        projections: dict[str, Projection],
        entries: dict[str, RegistryEntry],
        catalogues: dict[str, CatalogueEntry],
    ) -> None:
        self._projections = projections
        self._entries = entries
        self._catalogues = catalogues

    @classmethod
    def from_bundle(cls, bundle: SpecBundle) -> "InMemorySpecRegistry":
        from adlc.spec_toolkit.normalise import content_hash

        cats = Catalogues.from_bundle(bundle)
        terminals = {str(spec(t)["metadata"]["id"]): t for t in bundle.usable_terminals()}
        known = set(terminals)
        projections = {tid: project(spec(t), cats, known) for tid, t in terminals.items()}
        entries = {
            tid: RegistryEntry(
                tid, str(spec(t)["metadata"]["version"]), "active", content_hash(t.data), t.data
            )
            for tid, t in terminals.items()
        }
        catalogues = {
            name: CatalogueEntry(name, str(loaded.data.get("version")), loaded.data)
            for name, loaded in bundle.catalogues.items()
            if isinstance(loaded.data, dict)
        }
        return cls(projections, entries, catalogues)

    def _proj(self, terminal_id: str, version: str | None) -> Projection | None:
        entry = self._entries.get(terminal_id)
        if entry is None or (version is not None and version != entry.version):
            return None
        return self._projections.get(terminal_id)

    def terminals_opened_by(self, event_type: str) -> tuple[TerminalRef, ...]:
        return tuple(
            TerminalRef(tid, self._entries[tid].version)
            for tid, p in sorted(self._projections.items())
            if event_type in p.triggers
        )

    def outcome_route(
        self,
        terminal_id: str,
        status: str,
        root_cause: str | None = None,
        version: str | None = None,
    ) -> RouteTarget | None:
        proj = self._proj(terminal_id, version)
        return None if proj is None else _pick_route(list(proj.outcome_routes), status, root_cause)

    def event_route(
        self, terminal_id: str, event_type: str, version: str | None = None
    ) -> EventRouteTarget | None:
        proj = self._proj(terminal_id, version)
        for e in proj.event_routes if proj else ():
            if e.event_type == event_type:
                return _event(e)
        return None

    def change_class_route(
        self, terminal_id: str, change_class: str, version: str | None = None
    ) -> ChangeClassRoute | None:
        proj = self._proj(terminal_id, version)
        for c in proj.change_classes if proj else ():
            if c.change_class == change_class:
                return _change(c)
        return None

    def timeline(
        self, terminal_id: str, risk_tier: str, version: str | None = None
    ) -> TimelinePolicy | None:
        proj = self._proj(terminal_id, version)
        for t in proj.timelines if proj else ():
            if t.risk_tier == risk_tier:
                return _timeline(t)
        return None

    def entry(self, terminal_id: str, version: str | None = None) -> RegistryEntry | None:
        entry = self._entries.get(terminal_id)
        if entry is None or (version is not None and version != entry.version):
            return None
        return entry

    def catalogue(self, name: str) -> CatalogueEntry | None:
        return self._catalogues.get(name)


# ------------------------------------------------------------------ SQL


class SqlSpecRegistry:
    """Reads the spec schema (application identity, SELECT only)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _all(self, sql: str, **params: Any) -> list[Any]:
        with self._engine.connect() as conn:
            return list(conn.execute(text(sql), params).mappings())

    def terminals_opened_by(self, event_type: str) -> tuple[TerminalRef, ...]:
        rows = self._all(
            "SELECT r.terminal_id, r.version FROM spec.spec_trigger t "
            "JOIN spec.spec_registry r USING (spec_registry_id) "
            "WHERE t.event_type = :e AND r.status = 'active' ORDER BY r.terminal_id",
            e=event_type,
        )
        return tuple(TerminalRef(r["terminal_id"], r["version"]) for r in rows)

    def outcome_route(
        self,
        terminal_id: str,
        status: str,
        root_cause: str | None = None,
        version: str | None = None,
    ) -> RouteTarget | None:
        rows = self._all(
            "SELECT o.* FROM spec.spec_outcome_route o "
            "JOIN spec.spec_registry r USING (spec_registry_id) "
            "WHERE r.terminal_id = :t AND o.outcome_status = :s "
            "AND (CAST(:v AS text) IS NULL AND r.status = 'active' OR r.version = :v)",
            t=terminal_id,
            s=status,
            v=version,
        )
        routes = [
            OutcomeRoute(
                r["outcome_status"],
                r["root_cause"],
                r["destination_kind"],
                r["destination"],
                tuple(r["alternatives"]),
                tuple(r["requires"]),
                tuple(r["recheck_at"]),
                tuple(r["set_by"]),
                tuple(r["notify"]),
                r["condition"],
            )
            for r in rows
        ]
        return _pick_route(routes, status, root_cause)

    def event_route(
        self, terminal_id: str, event_type: str, version: str | None = None
    ) -> EventRouteTarget | None:
        rows = self._all(
            "SELECT e.* FROM spec.spec_event_route e "
            "JOIN spec.spec_registry r USING (spec_registry_id) "
            "WHERE r.terminal_id = :t AND e.event_type = :e "
            "AND (CAST(:v AS text) IS NULL AND r.status = 'active' OR r.version = :v)",
            t=terminal_id,
            e=event_type,
            v=version,
        )
        if not rows:
            return None
        r = rows[0]
        return EventRouteTarget(
            r["destination_kind"],
            r["destination"],
            tuple(r["immediate"]),
            r["then_destination"],
            tuple(r["notify"]),
            r["condition"],
        )

    def change_class_route(
        self, terminal_id: str, change_class: str, version: str | None = None
    ) -> ChangeClassRoute | None:
        rows = self._all(
            "SELECT c.* FROM spec.spec_change_class c "
            "JOIN spec.spec_registry r USING (spec_registry_id) "
            "WHERE r.terminal_id = :t AND c.change_class = :c "
            "AND (CAST(:v AS text) IS NULL AND r.status = 'active' OR r.version = :v)",
            t=terminal_id,
            c=change_class,
            v=version,
        )
        if not rows:
            return None
        r = rows[0]
        return ChangeClassRoute(
            r["reentry_terminal"],
            tuple(r["path"]),
            tuple(r["retrospective"]),
            r["within"],
            r["alternative"],
        )

    def timeline(
        self, terminal_id: str, risk_tier: str, version: str | None = None
    ) -> TimelinePolicy | None:
        rows = self._all(
            "SELECT t.* FROM spec.spec_timeline t "
            "JOIN spec.spec_registry r USING (spec_registry_id) "
            "WHERE r.terminal_id = :t AND t.risk_tier = :tier "
            "AND (CAST(:v AS text) IS NULL AND r.status = 'active' OR r.version = :v)",
            t=terminal_id,
            tier=risk_tier,
            v=version,
        )
        if not rows:
            return None
        r = rows[0]
        return TimelinePolicy(
            r["risk_tier"],
            r["expected_duration"],
            r["continuous"],
            r["reminder_after"],
            r["escalate_after"],
            r["escalate_at_window_end"],
            r["max_rework_cycles"],
            r["clarification_sla"],
            r["max_clarification_rounds"],
            r["max_auto_retries"],
            r["retirement_duration"],
        )

    def entry(self, terminal_id: str, version: str | None = None) -> RegistryEntry | None:
        rows = self._all(
            "SELECT r.* FROM spec.spec_registry r WHERE r.terminal_id = :t "
            "AND (CAST(:v AS text) IS NULL AND r.status = 'active' OR r.version = :v)",
            t=terminal_id,
            v=version,
        )
        if not rows:
            return None
        r = rows[0]
        return RegistryEntry(
            r["terminal_id"],
            r["version"],
            r["status"],
            r["content_hash"],
            r["spec_json"],
            r["registered_at"],
        )

    def catalogue(self, name: str) -> CatalogueEntry | None:
        rows = self._all(
            "SELECT catalogue_name, version, content_json FROM spec.spec_catalogue "
            "WHERE catalogue_name = :n AND status = 'active'",
            n=name,
        )
        if not rows:
            return None
        r = rows[0]
        return CatalogueEntry(r["catalogue_name"], r["version"], r["content_json"])
