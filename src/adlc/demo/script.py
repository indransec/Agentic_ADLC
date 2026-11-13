"""The demo script (feature 014, research R-01, data-model.md): steps with human actions, faults,
the demo moments they prove and the expected result. Data, validated on load; nothing here names
a terminal or a use case."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

MOMENTS = tuple(f"D-{n}" for n in range(1, 10))
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
}
EXPECTATIONS = ("state", "final_status", "run_number", "arrow", "escalated")


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
        if moment not in MOMENTS:
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
        actions.append(Action(kind, None if role is None else str(role), params))
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
