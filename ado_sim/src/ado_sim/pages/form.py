"""The work item form's model (feature 018, FR-002 to FR-004, FR-008; research R-02, R-06).

Everything here is driven by the process data (field types, allowed values, states, areas) and
the seed's form layout; no field or type of a use case is named.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from ado_sim.pages.sanitize import DROPPED_WITH_CONTENT, clean, web_address
from ado_sim.patch import REQUIRED_FIELDS
from ado_sim.process import FieldDef, FormSection, TypeInfo
from ado_sim.workitems import UpdateView

STATE = "System.State"
HIDDEN_TYPES = frozenset({"history"})  # the history field is the comments, shown on their own
HISTORY_SKIPPED = frozenset({"System.Rev", "System.ChangedDate", "System.ChangedBy"})
SHORT = 200
LINK_NAMES = {
    "System.LinkTypes.Hierarchy-Reverse": "parent",
    "System.LinkTypes.Hierarchy-Forward": "child",
    "System.LinkTypes.Related": "related",
}


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass
class FormField:
    ref: str
    label: str
    kind: str  # select, identity, text, textarea, number, datetime, readonly
    value: str
    choices: tuple[Choice, ...] = ()
    error: str | None = None
    link: str | None = None  # the value as a link when it is wholly an http(s) address
    formatted: str | None = None  # an HTML field's value, cleaned for display
    step: str | None = None  # a number input's step


@dataclass
class Section:
    title: str
    fields: list[FormField] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryChange:
    label: str
    old: str
    new: str
    old_short: str | None
    new_short: str | None


@dataclass(frozen=True)
class HistoryEntry:
    who: str
    when: str
    changes: tuple[HistoryChange, ...]
    links: list[str]


# ------------------------------------------------------------------------------ text of values


class _Text(HTMLParser):
    BLOCKS = frozenset({"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROPPED_WITH_CONTENT:
            self.skipping += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in DROPPED_WITH_CONTENT:
            self.skipping = max(0, self.skipping - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)


def html_text(value: str) -> str:
    """An HTML value as plain lines (how the form edits HTML fields)."""
    parser = _Text()
    parser.feed(value)
    parser.close()
    lines = (line.strip() for line in "".join(parser.parts).split("\n"))
    return "\n".join(line for line in lines if line)


def display_text(definition: FieldDef | None, value: Any) -> str:
    """A value as a person reads it."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("displayName") or value.get("uniqueName") or "")
    if isinstance(value, list):
        return ", ".join(display_text(None, v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if definition is not None and definition.type == "html":
        return html_text(str(value))
    return str(value)


def _input_text(definition: FieldDef, value: Any) -> str:
    """A value as its input holds it (what a save compares with)."""
    if value is None:
        return ""
    if definition.type == "identity" and isinstance(value, dict):
        return str(value.get("uniqueName") or "")
    if definition.type == "dateTime":
        return str(value)[:16]
    return _lines(display_text(definition, value))


def _lines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------------------------------ the form


def _kind(definition: FieldDef) -> str:
    if definition.read_only:
        return "readonly"
    if definition.reference_name == STATE or definition.type == "treePath":
        return "select"
    if definition.allowed_values is not None or definition.type == "boolean":
        return "select"
    return {
        "identity": "identity",
        "integer": "number",
        "double": "number",
        "dateTime": "datetime",
        "plainText": "textarea",
        "html": "textarea",
    }.get(definition.type, "text")


def _choices(
    definition: FieldDef,
    kind: TypeInfo,
    people: Iterable[Choice],
    areas: Iterable[str],
    current: str,
) -> tuple[Choice, ...]:
    if definition.reference_name == STATE:
        values = [Choice(s, s) for s in kind.state_names]
    elif definition.type == "treePath":
        values = [Choice(a, a) for a in areas]
    elif definition.type == "identity":
        values = list(people)
    elif definition.allowed_values is not None:
        values = [Choice(str(v), str(v)) for v in definition.allowed_values]
    else:  # boolean
        values = [Choice("true", "Yes"), Choice("false", "No")]
    if current and current not in [c.value for c in values]:
        values.append(Choice(current, current))
    if definition.reference_name not in REQUIRED_FIELDS:
        values.insert(0, Choice("", "—"))
    return tuple(values)


def _field(
    definition: FieldDef,
    kind: TypeInfo,
    values: Mapping[str, Any],
    people: Iterable[Choice],
    areas: Iterable[str],
    typed: Mapping[str, str],
    errors: Mapping[str, str],
) -> FormField:
    ref = definition.reference_name
    raw = values.get(ref)
    input_kind = _kind(definition)
    text = (
        display_text(definition, raw) if input_kind == "readonly" else _input_text(definition, raw)
    )
    if ref in typed:
        text = typed[ref]
    built = FormField(ref, definition.name, input_kind, text, error=errors.get(ref))
    if input_kind in ("select", "identity"):
        built.choices = _choices(definition, kind, people, areas, text)
    if input_kind == "number":
        built.step = "1" if definition.type == "integer" else "any"
    if definition.type == "html" and isinstance(raw, str) and raw.strip():
        built.formatted = clean(raw)
    if isinstance(raw, str) and definition.type != "html":
        built.link = web_address(raw)
    return built


def sections(
    kind: TypeInfo,
    layout: Iterable[FormSection],
    values: Mapping[str, Any],
    people: Iterable[Choice],
    areas: Iterable[str],
    *,
    typed: Mapping[str, str] | None = None,
    errors: Mapping[str, str] | None = None,
) -> list[Section]:
    """The form's sections: the layout's, then every other field of the type."""
    people, areas = tuple(people), tuple(areas)
    shown = [d for d in kind.fields.values() if d.type not in HIDDEN_TYPES]

    def build(definition: FieldDef) -> FormField:
        return _field(definition, kind, values, people, areas, typed or {}, errors or {})

    built: list[Section] = []
    placed: set[str] = set()
    for section in layout:
        refs = [kind.field(ref) for ref in section.fields]
        found = [d for d in refs if d is not None and d.type not in HIDDEN_TYPES]
        placed.update(d.reference_name for d in found)
        built.append(Section(section.title, [build(d) for d in found]))
    rest = sorted((d for d in shown if d.reference_name not in placed), key=lambda d: d.name)
    if rest:
        built.append(Section("Other fields" if built else "Fields", [build(d) for d in rest]))
    return built


def operations(
    kind: TypeInfo, at_rev: Mapping[str, Any], submitted: Mapping[str, str], rev: int
) -> list[dict[str, Any]]:
    """The patch for what the person changed against the revision the form was opened at."""
    changes: list[dict[str, Any]] = []
    for ref in sorted(submitted):
        definition = kind.field(ref)
        if definition is None or _kind(definition) == "readonly":
            continue
        if definition.type in HIDDEN_TYPES:
            continue
        new = _lines(submitted[ref])
        if definition.type not in ("plainText", "html"):
            new = new.strip()
        old = _input_text(definition, at_rev.get(definition.reference_name))
        if definition.type == "html":
            new = "\n".join(line.strip() for line in new.split("\n") if line.strip())
        if new == old:
            continue
        path = f"/fields/{definition.reference_name}"
        if not new.strip():
            changes.append({"op": "remove", "path": path})
            continue
        value: Any = new
        if definition.type == "html":
            value = "".join(f"<p>{html.escape(line, quote=False)}</p>" for line in new.split("\n"))
        changes.append({"op": "add", "path": path, "value": value})
    if not changes:
        return []
    return [{"op": "test", "path": "/rev", "value": rev}, *changes]


def field_of(kind: TypeInfo, message: str) -> str | None:
    """The field a refusal's message names, if it names one of the type's fields."""
    for ref in re.findall(r"[A-Za-z][\w]*\.[\w.]+", message):
        definition = kind.field(ref.rstrip("."))
        if definition is not None:
            return definition.reference_name
    return None


# ------------------------------------------------------------------------------ history


def _short(text: str) -> str | None:
    return text[:SHORT] + "…" if len(text) > SHORT else None


def history(
    updates: Iterable[UpdateView], kind: TypeInfo, title_of: Callable[[int], str]
) -> list[HistoryEntry]:
    """Every update, newest first: who, when, each changed field and each link change."""
    entries: list[HistoryEntry] = []
    for update in updates:
        when = (update.fields.get("System.ChangedDate") or {}).get(
            "newValue"
        ) or update.revised_date
        changes = []
        for ref, change in sorted(update.fields.items()):
            if ref in HISTORY_SKIPPED:
                continue
            definition = kind.field(ref)
            old = display_text(definition, change.get("oldValue"))
            new = display_text(definition, change.get("newValue"))
            label = definition.name if definition else ref
            changes.append(HistoryChange(label, old, new, _short(old), _short(new)))
        links = []
        for key, verb in (("added", "Linked"), ("removed", "Unlinked")):
            for relation in update.relations.get(key, []):
                target = int(relation["targetId"])
                name = LINK_NAMES.get(relation["rel"], relation["rel"])
                links.append(f"{verb} {name} {target}: {title_of(target)}")
        who = str(update.revised_by.get("displayName") or "")
        entries.append(HistoryEntry(who, str(when), tuple(changes), links))
    entries.reverse()
    return entries
