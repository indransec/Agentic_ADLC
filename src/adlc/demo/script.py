"""The demo script (feature 014, research R-01, data-model.md): steps with human actions, faults,
the demo moments they prove and the expected result. Data, validated on load; nothing here names
a terminal or a use case."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

MOMENTS = tuple(f"D-{n}" for n in range(1, 10))
# 020 (SA §22.10): shown only on the board, by board-only steps; optional in a script
BOARD_MOMENTS = frozenset({"D-12", "D-13"})
ITEM_KINDS = ("usecase", "run", "clarification", "change")  # the board items (tracker mapping)
# 020: actions that exist only on the board; a step with one is skipped when the sync is off
BOARD_ONLY = frozenset({"board_change", "drift", "reconcile"})
ACTIONS = {
    "submit": True,  # kind: needs a role
    "pass": False,
    "reject": True,
    "answer": False,
    "exception": True,
    "approve_change": False,
    "complete_escalation": True,
    "fault": False,
    "wait": False,
    "board_change": True,  # 020 D-12: a person changes a platform-written field
    "drift": False,  # 020 D-13: the operator changes one with the service account
    "reconcile": False,  # 020 D-13: the CoE reconciles
}
EXPECTATIONS = (
    "state",
    "final_status",
    "run_number",
    "arrow",
    "escalated",
    "reverted",  # 020: the changed field is back and the item has the platform's comment
    "reconciled",  # 020: the last reconciliation corrected the drifted field
)


class ScriptError(ValueError):
    """The script is invalid; the message names the step."""


@dataclass(frozen=True)
class Action:
    kind: str
    role: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Step:
    number: int
    usecase: str
    terminal: str
    proves: tuple[str, ...]
    say: str
    actions: tuple[Action, ...]
    expect: Mapping[str, Any]

    @property
    def board_only(self) -> bool:
        """020: the step shows something only the board has; skipped with the sync off."""
        return any(a.kind in BOARD_ONLY for a in self.actions)


@dataclass(frozen=True)
class DemoScript:
    usecases: Mapping[str, str]  # key → reference use case id
    recordings: str
    rehearsed: str  # "<module>:<function>" giving the rehearsed replies per agent
    steps: tuple[Step, ...]


def _step(raw: Mapping[str, Any], usecases: Mapping[str, str], roles: Collection[str]) -> Step:
    number = int(raw["number"])
    where = f"step {number}"
    if str(raw.get("usecase")) not in usecases:
        raise ScriptError(f"{where}: use case {raw.get('usecase')} is not in usecases")
    proves = tuple(str(m) for m in raw.get("proves") or ())
    for moment in proves:
        if moment not in MOMENTS and moment not in BOARD_MOMENTS:
            raise ScriptError(f"{where}: {moment} is not a demo moment")
    actions = []
    for item in raw.get("actions") or ():
        params = dict(item)
        kind = str(params.pop("kind", ""))
        if kind not in ACTIONS:
            raise ScriptError(f"{where}: unknown action {kind}")
        role = params.pop("role", None)
        if ACTIONS[kind] and role is None:
            raise ScriptError(f"{where}: action {kind} needs a role")
        if role is not None and role not in roles:
            raise ScriptError(f"{where}: role {role} is not in the role catalogue")
        if kind in ("board_change", "drift"):
            if not all(params.get(k) not in (None, "") for k in ("item", "field", "value")):
                raise ScriptError(f"{where}: {kind} needs item, field and value")
            if params["item"] not in ITEM_KINDS:
                raise ScriptError(
                    f"{where}: item {params['item']} is not a board item kind"
                    f" ({', '.join(ITEM_KINDS)})"
                )
        actions.append(Action(kind, None if role is None else str(role), params))
    board_only = any(a.kind in BOARD_ONLY for a in actions)
    for moment in proves:
        if board_only and moment in MOMENTS:
            raise ScriptError(f"{where}: {moment} cannot be proved by a board-only step")
        if not board_only and moment in BOARD_MOMENTS:
            raise ScriptError(f"{where}: {moment} is shown only by a board-only step")
    expect = dict(raw.get("expect") or {})
    for key in expect:
        if key not in EXPECTATIONS:
            raise ScriptError(f"{where}: unknown expectation {key}")
    return Step(
        number,
        str(raw["usecase"]),
        str(raw["terminal"]),
        proves,
        str(raw.get("say", "")),
        tuple(actions),
        expect,
    )


def load_script(path: Path, roles: Collection[str]) -> DemoScript:
    data = YAML(typ="safe").load(path.read_text())
    usecases = {str(k): str(v) for k, v in (data.get("usecases") or {}).items()}
    steps = tuple(_step(raw, usecases, roles) for raw in data.get("steps") or ())
    numbers = [s.number for s in steps]
    if numbers != sorted(set(numbers)):
        raise ScriptError("step numbers must be unique and in order")
    shown = {m for s in steps for m in s.proves}
    for moment in MOMENTS:
        if moment not in shown:
            raise ScriptError(f"{moment} is not shown by any step")
    return DemoScript(usecases, str(data["recordings"]), str(data["rehearsed"]), steps)
