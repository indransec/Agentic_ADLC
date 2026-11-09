"""Event and route graph over all terminal specs (research R-06).

Nodes: terminals (``T<n>``), events (``ev:<event>``), special destinations (``dest:<id>``),
external sources (``ext:<event>``) and one terminating sink (``END``). Edges follow
subscriptions (event → terminal), emitted events (terminal → event) and routes
(terminal → destination). Everything is derived from the specs and catalogues.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from adlc.spec_toolkit.catalogues import Catalogues
from adlc.spec_toolkit.loader import LoadedFile

TERMINAL_ID = re.compile(r"^T[0-9]+$")
EVENT = re.compile(r"^(T[0-9]+\.[a-z_]+(\.[A-Za-z0-9_]+)?|[a-z][a-z_]*\.[a-z][a-z_]*)$")
END = "END"


@dataclass(frozen=True)
class Destination:
    kind: str  # terminal | event | special | template | unknown
    value: str


@dataclass
class LifecycleGraph:
    graph: "nx.DiGraph[str]" = field(default_factory=nx.DiGraph)
    terminals: dict[str, LoadedFile] = field(default_factory=dict)
    emitted: dict[str, set[str]] = field(default_factory=dict)
    subscriptions: dict[str, list[str]] = field(default_factory=dict)

    def reaches(self, source: str, target: str) -> bool:
        if source == target:
            return True
        if source not in self.graph or target not in self.graph:
            return False
        return bool(nx.has_path(self.graph, source, target))

    def producers(self) -> set[str]:
        return {event for events in self.emitted.values() for event in events}


def body(loaded: LoadedFile) -> dict[str, Any]:
    data = loaded.data.get("terminal") if isinstance(loaded.data, dict) else None
    return data if isinstance(data, dict) else {}


def terminal_id(loaded: LoadedFile) -> str | None:
    value = body(loaded).get("metadata", {}).get("id")
    return value if isinstance(value, str) else None


def classify(value: str, cats: Catalogues, known_terminals: set[str]) -> Destination:
    if "${" in value:
        return Destination("template", value)
    if TERMINAL_ID.match(value):
        return Destination("terminal" if value in known_terminals else "unknown", value)
    if value in cats.route_destinations:
        return Destination("special", value)
    if EVENT.match(value):
        return Destination("event", value)
    return Destination("unknown", value)


def outcome_destinations(t: dict[str, Any]) -> Iterator[tuple[str, str, str]]:
    """(pointer, status, destination) for every route in outcome_model (not event routes)."""
    outcomes = t.get("outcome_model") or {}
    for status, outcome in outcomes.items():
        if status == "event_routes" or not isinstance(outcome, dict):
            continue
        base = f"/terminal/outcome_model/{status}"
        if isinstance(outcome.get("route"), str):
            yield f"{base}/route", status, outcome["route"]
        for cause, dest in (outcome.get("route_by_root_cause") or {}).items():
            if isinstance(dest, str):
                yield f"{base}/route_by_root_cause/{cause}", status, dest
        for i, dest in enumerate(outcome.get("alternatives") or []):
            if isinstance(dest, str):
                yield f"{base}/alternatives/{i}", status, dest
        if isinstance(outcome.get("then"), str):
            yield f"{base}/then", status, outcome["then"]


def event_route_destinations(t: dict[str, Any]) -> Iterator[tuple[str, str, str]]:
    for event, route in ((t.get("outcome_model") or {}).get("event_routes") or {}).items():
        if not isinstance(route, dict):
            continue
        base = f"/terminal/outcome_model/event_routes/{event}"
        for key in ("route", "then"):
            if isinstance(route.get(key), str):
                yield f"{base}/{key}", event, route[key]


def emitted_events(tid: str, t: dict[str, Any]) -> set[str]:
    outcomes = t.get("outcome_model") or {}
    events = {f"{tid}.pass", f"{tid}.escalate", f"{tid}.terminate"}
    if not (outcomes.get("exception") or {}).get("not_allowed"):
        events.add(f"{tid}.exception")
    for cause in (outcomes.get("rework") or {}).get("route_by_root_cause") or {}:
        events.add(f"{tid}.rework.{cause}")
    if (t.get("controls") or {}).get("auto_rollback_on"):
        events.add(f"{tid}.rollback")
    for monitor in t.get("monitors") or []:
        if isinstance(monitor, dict) and isinstance(monitor.get("raises"), str):
            events.add(monitor["raises"])
    for change in (t.get("change_classes") or {}).values():
        if isinstance(change, dict) and isinstance(change.get("reentry"), str):
            events.add(f"{tid}.reentry.{change['reentry']}")
    for _, _, dest in event_route_destinations(t):
        if EVENT.match(dest) and not TERMINAL_ID.match(dest):
            events.add(dest)
    return events


def build_graph(terminals: list[LoadedFile], cats: Catalogues) -> LifecycleGraph:
    lg = LifecycleGraph()
    for loaded in terminals:
        tid = terminal_id(loaded)
        if tid is not None and tid not in lg.terminals:
            lg.terminals[tid] = loaded
    known = set(lg.terminals)
    g = lg.graph
    g.add_node(END)
    for event in cats.external_events:
        g.add_edge(f"ext:{event}", f"ev:{event}")
    for dest_id, kind in cats.route_destinations.items():
        g.add_node(f"dest:{dest_id}")
        if kind == "terminating":
            g.add_edge(f"dest:{dest_id}", END)
    for tid, loaded in lg.terminals.items():
        t = body(loaded)
        g.add_node(tid)
        triggers = [e for e in (t.get("trigger") or {}).get("on") or [] if isinstance(e, str)]
        lg.subscriptions[tid] = triggers
        for event in triggers:
            g.add_edge(f"ev:{event}", tid)
        lg.emitted[tid] = emitted_events(tid, t)
        for event in lg.emitted[tid]:
            g.add_edge(tid, f"ev:{event}")
        if not ((t.get("outcome_model") or {}).get("terminate") or {}).get("not_allowed"):
            g.add_edge(tid, END)
        reentries = [
            c["reentry"]
            for c in (t.get("change_classes") or {}).values()
            if isinstance(c, dict) and isinstance(c.get("reentry"), str)
        ]
        for _, _, dest in [*outcome_destinations(t), *event_route_destinations(t)]:
            d = classify(dest, cats, known)
            if d.kind == "terminal":
                g.add_edge(tid, d.value)
            elif d.kind == "event":
                g.add_edge(tid, f"ev:{d.value}")
            elif d.kind == "special":
                g.add_edge(tid, f"dest:{d.value}")
            elif d.kind == "template":
                for target in reentries:
                    if target in known:
                        g.add_edge(tid, target)
    return lg
