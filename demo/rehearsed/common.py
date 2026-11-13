"""Rehearsed agent replies for the acting terminals (feature 014, research R-02): what a correct
agent does with its tools, reading tool results and evidence from the conversation the way a model
would, so values produced by the run (package hashes, result ids, change ids) are copied, never
recorded. The demo driver and the tests use the same programs.

These are demo assets for the reference use case (incident triage on the pilot), outside the
platform package: use-case values belong here, never in ``src/adlc``.

Shared helpers."""

import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from adlc.policy.synthetic import load_synthetic_artifacts

SYNTHETIC = Path(
    os.environ.get("ADLC_SYNTHETIC_DIR") or Path(__file__).parents[2] / "data" / "synthetic"
)
SYN = load_synthetic_artifacts(SYNTHETIC)
# the pilot's resolver teams (pilot/template), mapped to the reference requirements
TEAMS = ("service-desk", "identity-access", "network-ops", "security-ops", "app-support")
Messages = Sequence[Mapping[str, str]]
Reply = Callable[[Messages], str]
FILL = {
    "instructions.md": "Assign each incident to its resolver team; never close incidents.",
    "routing_rules.yaml": "a: 2",
}
REQS = {team: f"FR-0{i}" for i, team in enumerate(TEAMS, start=1)}


def all_outputs(messages: Messages, name: str) -> list[dict[str, Any]]:
    marker = f'<data source="tool:{name}">'
    found = []
    for message in messages:
        content = message["content"]
        if message["role"] == "user" and marker in content:
            found.append(
                json.loads(content[content.index(marker) + len(marker) : content.rindex("</data>")])
            )
    return found


def output_of(messages: Messages, name: str) -> dict[str, Any]:
    found = all_outputs(messages, name)
    if not found:
        raise AssertionError(f"no {name} output in the conversation")
    return found[-1]


def evidence(messages: Messages) -> dict[str, Any]:
    marker = '<data source="evidence">'
    for message in messages:
        content = message["content"]
        if marker in content:
            body = content[content.index(marker) + len(marker) :]
            found: dict[str, Any] = json.loads(body[: body.index("</data>")])
            return found
    return {}


def rows_of(messages: Messages, terminal: str, artifact: str) -> list[dict[str, Any]]:
    """An earlier terminal's artifact rows from the evidence block (``artifacts.<id>.rows``)."""
    found = ((evidence(messages).get(terminal) or {}).get("artifacts") or {}).get(artifact) or {}
    rows = found.get("rows") if isinstance(found, dict) else None
    return list(rows) if isinstance(rows, list) else []


def tool(name: str, arguments: Mapping[str, Any] | None = None) -> str:
    """A reply that calls one tool."""
    return json.dumps({"tool": {"name": name, "arguments": dict(arguments or {})}})
