"""Scriptable stand-ins for the policy engine, agent and reviewer (research R-10).

They implement the same protocols as the real components (constitution VII), so features 004
and 006 replace them without touching the orchestrator. Scripts are plain dictionaries:

* ``StubAgent(script={<terminal>: {1: Clarification(...)}})`` answers that terminal's first
  build with a clarification. A ``dict`` entry overrides artifact cells:
  ``{<artifact>: {<column>: <value>}}``.
* ``StubReviewer(script={<terminal>: {1: Recommendation("rework")}})``.
* ``StubPolicy(script={(<terminal>, <check id>): False})``.
"""

import copy
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import (
    AgentResult,
    Artifacts,
    BuildContext,
    EvalContext,
    EvalResult,
    Recommendation,
    ReviewContext,
    ReviewResult,
)

AgentScript = Mapping[str, Mapping[int, AgentResult | Mapping[str, Mapping[str, Any]]]]


class StubPolicy:
    def __init__(self, script: Mapping[tuple[str, str], Any] | None = None) -> None:
        self.script = dict(script or {})
        self.calls: list[tuple[str, str]] = []

    def evaluate(self, expression: str, context: EvalContext) -> EvalResult:
        self.calls.append((context.terminal_id, context.check_id))
        value = self.script.get((context.terminal_id, context.check_id), True)
        return EvalResult(passed=bool(value), value=value, reason="stub")

    def authorize(self, actor: str, action: str, resource: str, context: EvalContext) -> bool:
        return bool(self.script.get((context.terminal_id, f"authorize:{action}"), True))


class StubAgent:
    """``base`` gives starting artifacts per terminal (the synthetic data of feature 004);
    terminals without a base get placeholder rows."""

    def __init__(
        self,
        script: AgentScript | None = None,
        base: Mapping[str, Mapping[str, list[dict[str, Any]]]] | None = None,
    ) -> None:
        self.script = script or {}
        self.base = dict(base or {})
        self.calls: dict[str, int] = defaultdict(int)
        self.contexts: list[BuildContext] = []

    def build(self, context: BuildContext) -> AgentResult:
        self.calls[context.terminal_id] += 1
        self.contexts.append(context)
        entry = self.script.get(context.terminal_id, {}).get(self.calls[context.terminal_id])
        if entry is not None and not isinstance(entry, Mapping):
            return entry
        overrides: Mapping[str, Mapping[str, Any]] = entry or {}
        base = self.base.get(context.terminal_id, {})
        artifacts: dict[str, list[dict[str, Any]]] = {
            a.id: copy.deepcopy(base[a.id])
            if a.id in base
            else [{column: f"{column} (stub)" for column in a.columns}]
            for a in spec_view.artifacts(context.spec)
        }
        for artifact_id, cells in overrides.items():
            empty: list[dict[str, Any]] = [{}]
            artifacts.setdefault(artifact_id, empty)[0].update(cells)
        return Artifacts(artifacts)


class StubReviewer:
    def __init__(self, script: Mapping[str, Mapping[int, ReviewResult]] | None = None) -> None:
        self.script = script or {}
        self.calls: dict[str, int] = defaultdict(int)
        self.contexts: list[ReviewContext] = []

    def review(self, context: ReviewContext) -> ReviewResult:
        self.calls[context.terminal_id] += 1
        self.contexts.append(context)
        scripted = self.script.get(context.terminal_id, {}).get(self.calls[context.terminal_id])
        if scripted is not None:
            return scripted
        return Recommendation("pass", {item: 1 for item in context.checklist_items})
