"""The tracker mapping at run time (contracts/tracker-mapping.md; research R-12).

Loads ``adlc-specs/tracker_mapping.yaml`` (validated against its schema next to it), answers every
"what is X called on the board" question, and checks the mapping against a board's process. The
spec toolkit's rules V-32..V-36 check it against the terminal specs; this module never names a
tracker value itself.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from adlc.config.durations import DurationError, parse_duration
from adlc.engagement.model import BoardInfo

KINDS = ("usecase", "run", "clarification", "change")
# 020: the decisions made on a change request item; every other decision value is a run's
CHANGE_ACTIONS = ("approve_change", "reject_change")
SCHEMA = Path("schema") / "catalogues" / "tracker_mapping.schema.json"


class MappingError(ValueError):
    """The mapping file cannot be read or does not match its schema; names file and path."""


@dataclass(frozen=True)
class ItemSpec:
    kind: str
    type: str
    fields: Mapping[str, str]  # mapping key -> field reference
    parent: str | None


@dataclass(frozen=True)
class InputSpec:
    field: str
    label: str


class TrackerMapping:
    def __init__(self, data: Mapping[str, Any], source: str = "<memory>") -> None:
        self.source = source
        self._data = data
        items = data["items"]
        self._items = {
            kind: ItemSpec(
                kind,
                str(items[kind]["type"]),
                {str(k): str(v) for k, v in items[kind]["fields"].items()},
                items[kind].get("parent"),
            )
            for kind in KINDS
        }
        try:
            self.poll_interval: timedelta = parse_duration(str(data["inbound"]["poll_interval"]))
        except DurationError as error:
            raise MappingError(f"{source}: /inbound/poll_interval: {error}") from None
        self.area = str(data["area"])
        self.identity_match = str(data["identities"]["match"])
        decision = data["decision"]
        self.decision_field = str(decision["field"])
        self.comment_field = str(decision["comment"])
        self._values = {str(k): str(v) for k, v in decision["values"].items()}
        self._by_value = {v.strip().lower(): k for k, v in self._values.items()}
        self._inputs = {
            str(k): InputSpec(str(v["field"]), str(v["label"]))
            for k, v in decision["inputs"].items()
        }

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, path: Path, spec_root: Path | None = None) -> TrackerMapping:
        """Load and schema-check ``path``; the schema is under ``spec_root`` (default: the file's
        folder, which is the spec folder for ``adlc-specs/tracker_mapping.yaml``)."""
        try:
            data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
        except (OSError, YAMLError) as error:
            raise MappingError(
                f"{path}: cannot read the tracker mapping ({type(error).__name__})"
            ) from None
        schema_path = (spec_root or path.parent) / SCHEMA
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise MappingError(
                f"{schema_path}: cannot read the schema ({type(error).__name__})"
            ) from None
        errors = sorted(
            Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path)
        )
        if errors:
            problems = [
                f"/{'/'.join(str(p) for p in error.absolute_path)}: {error.message}"
                for error in errors
            ]
            raise MappingError(f"{path}:\n  " + "\n  ".join(problems))
        return cls(data, str(path))

    # ------------------------------------------------------------------ queries

    def item(self, kind: str) -> ItemSpec:
        return self._items[kind]

    def kind_of_type(self, item_type: str) -> str | None:
        for kind, spec in self._items.items():
            if spec.type == item_type:
                return kind
        return None

    def field(self, kind: str, key: str) -> str:
        return self._items[kind].fields[key]

    def column(self, terminal_id: str) -> str | None:
        columns: Mapping[str, str] = self._data["items"]["usecase"]["columns"]
        value = columns.get(terminal_id)
        return None if value is None else str(value)

    @property
    def closed_column(self) -> str:
        return str(self._data["items"]["usecase"]["closed"])

    def terminated_state(self, kind: str) -> str:
        return str(self._data["items"][kind]["terminated"])

    def run_item_state(self, run_state: str) -> str:
        return str(self._data["items"]["run"]["states"][run_state])

    def sub_stage(self, run_state: str) -> str:
        return str(self._data["sub_stages"][run_state])

    @property
    def clarification_open(self) -> str:
        return str(self._data["items"]["clarification"]["open"])

    @property
    def clarification_answered(self) -> str:
        return str(self._data["items"]["clarification"]["answered"])

    def change_state(self, status: str) -> str:
        """020: the item state for a change request that is ``awaiting``, ``approved`` or
        ``rejected``."""
        return str(self._data["items"]["change"]["states"][status])

    def kind_of_action(self, action: str) -> str:
        """020: the kind of item a decision is made on (``change`` or ``run``)."""
        return "change" if action in CHANGE_ACTIONS else "run"

    def value_for(self, action: str) -> str:
        return self._values[action]

    def action_for(self, value: object) -> str | None:
        """The platform action a decision value names (case and surrounding spaces ignored)."""
        if not isinstance(value, str):
            return None
        return self._by_value.get(value.strip().lower())

    def allowed_values(self, kind: str | None = None) -> list[str]:
        """The decision values, or only those made on ``kind``'s items (020)."""
        return [
            value
            for action, value in self._values.items()
            if kind is None or self.kind_of_action(action) == kind
        ]

    def inputs(self) -> Mapping[str, InputSpec]:
        return dict(self._inputs)

    def person_input_fields(self, kind: str) -> set[str]:
        """Fields people fill to make a request: decision, comment and inputs; or the answer."""
        if kind == "run":
            return {self.decision_field, self.comment_field} | {
                spec.field for spec in self._inputs.values()
            }
        if kind == "clarification":
            return {self.field("clarification", "answer")}
        if kind == "change":
            return {self.decision_field, self.comment_field}
        return set()

    def platform_written(self, kind: str) -> set[str]:
        keys = self._data["platform_written"].get(kind) or []
        return {self.field(kind, str(key)) for key in keys}

    def states_used(self, kind: str) -> set[str]:
        """Every board state the platform writes for this kind of item."""
        items = self._data["items"]
        if kind == "usecase":
            return {*map(str, items["usecase"]["columns"].values()), self.closed_column} | {
                self.terminated_state("usecase")
            }
        if kind == "run":
            return {*map(str, items["run"]["states"].values()), self.terminated_state("run")}
        if kind == "change":
            return {str(v) for v in items["change"]["states"].values()}
        return {self.clarification_open, self.clarification_answered}

    def names(self) -> set[str]:
        """Every name the board defines that the mapping uses (for the no-hard-coded-values scan,
        FR-003): types, states, columns, sub-stages, fields, decision values and the area."""
        found: set[str] = {self.area, self.decision_field, self.comment_field}
        for kind in KINDS:
            spec = self._items[kind]
            found |= {spec.type, *spec.fields.values(), *self.states_used(kind)}
        found |= set(self._values.values()) | {str(v) for v in self._data["sub_stages"].values()}
        # Input labels ("reason", "value"...) are the platform's own words for reading a
        # comment, not names the board defines, so they are not tracker names.
        found |= {given.field for given in self._inputs.values()}
        return found

    # ------------------------------------------------------------------ board check

    def check_against(self, board: BoardInfo) -> list[str]:
        """Every way the board lacks what the mapping names; empty when it fits (R-12)."""
        gaps: list[str] = []
        for kind in KINDS:
            spec = self._items[kind]
            offered = board.types.get(spec.type)
            if offered is None:
                gaps.append(f"{kind}: the board has no work item type {spec.type!r}")
                continue
            needed = set(spec.fields.values()) | self.person_input_fields(kind)
            for field in sorted(needed - offered.fields - _ALWAYS_PRESENT):
                gaps.append(f"{kind}: type {spec.type!r} has no field {field}")
            for state in sorted(self.states_used(kind) - set(offered.states)):
                gaps.append(f"{kind}: type {spec.type!r} has no state {state!r}")
        if self.area not in board.areas:
            gaps.append(f"the board has no area path '{self.area}'")
        return gaps


# Fields every work item has whether or not a type lists them (none today; kept explicit).
_ALWAYS_PRESENT: frozenset[str] = frozenset()
