"""Transactional registration of specs, catalogues and playbooks (research R-12; FR-018–FR-023).

One owner-identity transaction, serialised by a PostgreSQL advisory lock. Unchanged items are
skipped; changed content under an already registered version, an insufficient version bump,
or any validation error refuses the whole registration and writes nothing.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, text

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.loader import LoadedFile, SpecBundle, load_bundle
from adlc.spec_toolkit.normalise import content_hash, file_hash
from adlc.spec_toolkit.projections import Projection, project
from adlc.spec_toolkit.rules import Context, validate
from adlc.spec_toolkit.rules.single_spec import spec
from adlc.spec_toolkit.rules.versioning import bump_between, compare, parse_semver

log = logging.getLogger("adlc.spec_toolkit.register")
LOCK_KEY = "adlc.spec.register"


class RegistrationRefused(Exception):
    """Registration refused; nothing was written."""


class _DryRun(Exception):
    pass


@dataclass(frozen=True)
class ItemResult:
    kind: str  # terminal | catalogue | playbook | prompt
    name: str
    version: str
    action: str  # registered | unchanged
    previous: str | None = None


@dataclass
class RegistrationReport:
    items: list[ItemResult] = field(default_factory=list)
    dry_run: bool = False

    @property
    def registered_count(self) -> int:
        return sum(1 for i in self.items if i.action == "registered")

    @property
    def unchanged_count(self) -> int:
        return sum(1 for i in self.items if i.action == "unchanged")

    def lines(self) -> list[str]:
        out: list[str] = []
        for item in self.items:
            if item.action == "registered" and item.previous:
                out.append(
                    f"{item.name} {item.previous} → {item.version}  registered "
                    f"(deprecated {item.previous})"
                )
            else:
                out.append(f"{item.name} {item.version}  {item.action}")
        prefix = "dry run, rolled back: " if self.dry_run else ""
        out.append(
            f"spec registration: {prefix}{self.registered_count} registered, "
            f"{self.unchanged_count} unchanged, 0 refused"
        )
        return out


def _check_bump(name: str, old_version: str, new_version: str, old: Any, new: Any) -> None:
    old_v, new_v = parse_semver(old_version), parse_semver(new_version)
    if old_v is None or new_v is None:
        raise RegistrationRefused(f"{name}: invalid version")
    if new_v < old_v:
        raise RegistrationRefused(
            f"{name}: version {new_version} is lower than registered {old_version}"
        )
    needed = compare(old, new)
    if needed > bump_between(old_v, new_v):
        raise RegistrationRefused(
            f"{name}: {needed.name.lower()} change needs a {needed.name.lower()} version bump "
            f"(registered {old_version}, file {new_version})"
        )


def _rows(conn: Connection, sql: str, **params: Any) -> list[Any]:
    return list(conn.execute(text(sql), params).mappings())


def _register_catalogue(conn: Connection, name: str, loaded: LoadedFile) -> ItemResult:
    data = loaded.data
    version = str(data["version"])
    digest = content_hash(data)
    same = _rows(
        conn,
        "SELECT status, content_hash FROM spec.spec_catalogue "
        "WHERE catalogue_name=:n AND version=:v",
        n=name,
        v=version,
    )
    if same:
        if same[0]["content_hash"] != digest:
            raise RegistrationRefused(
                f"catalogue {name}: content changed but version {version} is already registered"
            )
        if same[0]["status"] != "active":
            raise RegistrationRefused(
                f"catalogue {name}: version {version} is registered as {same[0]['status']}"
            )
        return ItemResult("catalogue", name, version, "unchanged")
    active = _rows(
        conn,
        "SELECT version, content_json FROM spec.spec_catalogue "
        "WHERE catalogue_name=:n AND status='active'",
        n=name,
    )
    previous = None
    if active:
        previous = str(active[0]["version"])
        _check_bump(f"catalogue {name}", previous, version, active[0]["content_json"], data)
        conn.execute(
            text(
                "UPDATE spec.spec_catalogue SET status='deprecated', deprecated_at=now() "
                "WHERE catalogue_name=:n AND status='active'"
            ),
            {"n": name},
        )
    conn.execute(
        text(
            "INSERT INTO spec.spec_catalogue "
            "(catalogue_name, version, status, content_json, content_hash) "
            "VALUES (:n, :v, 'active', CAST(:j AS jsonb), :h)"
        ),
        {"n": name, "v": version, "j": json.dumps(data), "h": digest},
    )
    return ItemResult("catalogue", name, version, "registered", previous)


def _insert_projection(conn: Connection, registry_id: int, proj: Projection) -> None:
    for event in proj.triggers:
        conn.execute(
            text("INSERT INTO spec.spec_trigger (spec_registry_id, event_type) VALUES (:r, :e)"),
            {"r": registry_id, "e": event},
        )
    for r in proj.outcome_routes:
        conn.execute(
            text(
                "INSERT INTO spec.spec_outcome_route "
                "(spec_registry_id, outcome_status, root_cause, "
                "destination_kind, destination, alternatives, requires, recheck_at, set_by, "
                "notify, "
                "condition) VALUES (:r, :s, :c, :k, :d, :alt, :req, :rec, :set, :notify, :cond)"
            ),
            {
                "r": registry_id,
                "s": r.outcome_status,
                "c": r.root_cause,
                "k": r.destination_kind,
                "d": r.destination,
                "alt": list(r.alternatives),
                "req": list(r.requires),
                "rec": list(r.recheck_at),
                "set": list(r.set_by),
                "notify": list(r.notify),
                "cond": r.condition,
            },
        )
    for e in proj.event_routes:
        conn.execute(
            text(
                "INSERT INTO spec.spec_event_route "
                "(spec_registry_id, event_type, destination_kind, "
                "destination, immediate, then_destination, notify, condition) "
                "VALUES (:r, :e, :k, :d, :imm, :then, :notify, :cond)"
            ),
            {
                "r": registry_id,
                "e": e.event_type,
                "k": e.destination_kind,
                "d": e.destination,
                "imm": list(e.immediate),
                "then": e.then_destination,
                "notify": list(e.notify),
                "cond": e.condition,
            },
        )
    for c in proj.change_classes:
        conn.execute(
            text(
                "INSERT INTO spec.spec_change_class "
                "(spec_registry_id, change_class, reentry_terminal, "
                "path, retrospective, within, alternative) "
                "VALUES (:r, :c, :t, :p, :retro, :w, :alt)"
            ),
            {
                "r": registry_id,
                "c": c.change_class,
                "t": c.reentry_terminal,
                "p": list(c.path),
                "retro": list(c.retrospective),
                "w": c.within,
                "alt": c.alternative,
            },
        )
    for t in proj.timelines:
        conn.execute(
            text(
                "INSERT INTO spec.spec_timeline (spec_registry_id, risk_tier, expected_duration, "
                "continuous, reminder_after, escalate_after, escalate_at_window_end, "
                "max_rework_cycles, "
                "clarification_sla, max_clarification_rounds, max_auto_retries, retirement_duration) "
                "VALUES (:r, :tier, :exp, :cont, :rem, :esc, :win, :rework, :sla, :rounds, :retries, :ret)"
            ),
            {
                "r": registry_id,
                "tier": t.risk_tier,
                "exp": t.expected_duration,
                "cont": t.continuous,
                "rem": t.reminder_after,
                "esc": t.escalate_after,
                "win": t.escalate_at_window_end,
                "rework": t.max_rework_cycles,
                "sla": t.clarification_sla,
                "rounds": t.max_clarification_rounds,
                "retries": t.max_auto_retries,
                "ret": t.retirement_duration,
            },
        )


def _register_terminal(
    conn: Connection, loaded: LoadedFile, cats: Catalogues, known: set[str]
) -> ItemResult:
    body = spec(loaded)
    meta = body["metadata"]
    tid, version = str(meta["id"]), str(meta["version"])
    digest = content_hash(loaded.data)
    same = _rows(
        conn,
        "SELECT status, content_hash FROM spec.spec_registry WHERE terminal_id=:t AND version=:v",
        t=tid,
        v=version,
    )
    if same:
        if same[0]["content_hash"] != digest:
            raise RegistrationRefused(
                f"{tid}: content changed but version {version} is already registered"
            )
        if same[0]["status"] != "active":
            raise RegistrationRefused(
                f"{tid}: version {version} is registered as {same[0]['status']}"
            )
        return ItemResult("terminal", tid, version, "unchanged")
    active = _rows(
        conn,
        "SELECT version, spec_json FROM spec.spec_registry WHERE terminal_id=:t AND status='active'",
        t=tid,
    )
    previous = None
    if active:
        previous = str(active[0]["version"])
        _check_bump(tid, previous, version, active[0]["spec_json"], loaded.data)
        conn.execute(
            text(
                "UPDATE spec.spec_registry SET status='deprecated', deprecated_at=now() "
                "WHERE terminal_id=:t AND status='active'"
            ),
            {"t": tid},
        )
    proj = project(body, cats, known)
    registry_id = int(
        conn.execute(
            text(
                "INSERT INTO spec.spec_registry (terminal_id, version, status, schema_version, spec_yaml, "
                "spec_json, content_hash, trigger_events, emitted_events) VALUES (:t, :v, 'active', :sv, "
                ":yaml, CAST(:json AS jsonb), :h, :trig, :emit) RETURNING spec_registry_id"
            ),
            {
                "t": tid,
                "v": version,
                "sv": str(meta.get("schema_version")),
                "yaml": loaded.text,
                "json": json.dumps(loaded.data),
                "h": digest,
                "trig": list(proj.triggers),
                "emit": list(proj.emitted_events),
            },
        ).scalar_one()
    )
    _insert_projection(conn, registry_id, proj)
    return ItemResult("terminal", tid, version, "registered", previous)


def _register_playbook(conn: Connection, loaded: LoadedFile) -> ItemResult:
    data = loaded.data
    pid, version = str(data["id"]), str(data["version"])
    digest = file_hash(loaded.text)
    same = _rows(
        conn,
        "SELECT content_hash FROM spec.playbook_registry WHERE playbook_id=:p AND version=:v",
        p=pid,
        v=version,
    )
    if same:
        if same[0]["content_hash"] != digest:
            raise RegistrationRefused(
                f"{pid}: playbook changed but version {version} is already registered"
            )
        return ItemResult("playbook", pid, version, "unchanged")
    conn.execute(
        text(
            "INSERT INTO spec.playbook_registry (playbook_id, version, path, content_hash) "
            "VALUES (:p, :v, :path, :h)"
        ),
        {"p": pid, "v": version, "path": loaded.rel, "h": digest},
    )
    return ItemResult("playbook", pid, version, "registered")


def _register_prompt(conn: Connection, loaded: LoadedFile) -> ItemResult:
    """Prompts are registered like playbooks (feature 006): a changed body needs a new version."""
    data = loaded.data
    pid, version = str(data["id"]), str(data["version"])
    digest = file_hash(loaded.text)
    same = _rows(
        conn,
        "SELECT content_hash FROM spec.prompt_registry WHERE prompt_id=:p AND version=:v",
        p=pid,
        v=version,
    )
    if same:
        if same[0]["content_hash"] != digest:
            raise RegistrationRefused(
                f"{pid}: prompt changed but version {version} is already registered"
            )
        return ItemResult("prompt", pid, version, "unchanged")
    conn.execute(
        text(
            "INSERT INTO spec.prompt_registry (prompt_id, version, path, content_hash) "
            "VALUES (:p, :v, :path, :h)"
        ),
        {"p": pid, "v": version, "path": loaded.rel, "h": digest},
    )
    return ItemResult("prompt", pid, version, "registered")


def _validated(root: Path) -> SpecBundle:
    bundle = load_bundle(root)
    errors = [f for f in validate(Context(bundle)) if f.severity == "error"]
    if errors:
        details = "; ".join(f"{f.location()} {f.rule_id} {f.message}" for f in errors[:10])
        raise RegistrationRefused(f"{len(errors)} validation errors: {details}")
    return bundle


def register(root: Path, engine: Engine, *, dry_run: bool = False) -> RegistrationReport:
    """Validate the spec folder, then register everything new in one transaction."""
    bundle = _validated(root)
    cats = Catalogues.from_bundle(bundle)
    terminals = sorted(bundle.terminals.values(), key=lambda t: spec(t)["metadata"]["id"])
    known = {str(spec(t)["metadata"]["id"]) for t in terminals}
    report = RegistrationReport(dry_run=dry_run)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": LOCK_KEY})
            for name, loaded in sorted(bundle.catalogues.items()):
                report.items.append(_register_catalogue(conn, name, loaded))
            for loaded in terminals:
                report.items.append(_register_terminal(conn, loaded, cats, known))
            for loaded in sorted(bundle.playbooks.values(), key=lambda p: p.rel):
                report.items.append(_register_playbook(conn, loaded))
            for loaded in sorted(bundle.prompts.values(), key=lambda p: p.rel):
                report.items.append(_register_prompt(conn, loaded))
            if dry_run:
                raise _DryRun
    except _DryRun:
        pass
    log.info(
        "spec registration: %s registered, %s unchanged%s",
        report.registered_count,
        report.unchanged_count,
        " (dry run)" if dry_run else "",
    )
    return report
