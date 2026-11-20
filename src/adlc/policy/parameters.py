"""Parameter resolution within enterprise guardrails (SA §5.4; FR-012 to FR-014; research R-06).

Pure: ``resolve(guardrails, tier, profile)``. A use-case value is used only when it is within the
guardrail for the tier: stricter or equal (lower for ``max``, higher for ``min``, a superset for
``superset``). Anything else is rejected with the reason, and the tier value applies. The frozen
set per run is written by ``ParameterService``.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from sqlalchemy import Engine, text

from adlc.db.engine import write_independently
from adlc.orchestration.interfaces import EvalContext
from adlc.policy.evidence import Answer, Evidence
from adlc.policy.values import NOT_AVAILABLE, as_number

DEFAULT_TIER = "medium"


@dataclass(frozen=True)
class Rejected:
    name: str
    proposed: Any
    tier_value: Any
    reason: str


@dataclass(frozen=True)
class ResolvedParameters:
    tier: str
    values: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    rejected: tuple[Rejected, ...] = ()
    unresolved: tuple[str, ...] = ()


def _within(direction: str, proposed: Any, tier_value: Any) -> str | None:
    """None when ``proposed`` is within the guardrail, else the reason it is not."""
    if direction == "superset":
        if not isinstance(proposed, list):
            return "not a list"
        missing = sorted(set(map(str, tier_value or [])) - set(map(str, proposed)))
        return None if not missing else f"drops required {', '.join(missing)}"
    number, limit = as_number(proposed), as_number(tier_value)
    if number is None:
        return "not numeric"
    if limit is None:
        return "guardrail has no numeric tier value"
    if direction == "max" and number > limit:
        return f"{number} is looser than the maximum {limit}"
    if direction == "min" and number < limit:
        return f"{number} is looser than the minimum {limit}"
    return None


def resolve(
    guardrails: Sequence[Mapping[str, Any]], tier: str | None, profile: Mapping[str, Any]
) -> ResolvedParameters:
    tier = tier or DEFAULT_TIER
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    rejected: list[Rejected] = []
    unresolved: list[str] = []
    for guardrail in guardrails:
        name = str(guardrail["name"])
        tier_values = guardrail.get("values") or {}
        if tier not in tier_values or tier_values[tier] is None:
            unresolved.append(name)
            continue
        tier_value = tier_values[tier]
        values[name], sources[name] = tier_value, "guardrail"
        if name not in profile:
            continue
        reason = _within(str(guardrail.get("direction", "")), profile[name], tier_value)
        if reason is None:
            values[name], sources[name] = profile[name], "usecase"
        else:
            rejected.append(Rejected(name, profile[name], tier_value, reason))
    return ResolvedParameters(tier, values, sources, tuple(rejected), tuple(unresolved))


class ProfileSource(Protocol):
    """Use-case values (005: the profile version the run opened with, when ``run_id`` is given)."""

    def values(self, usecase_id: str, run_id: str | None = None) -> Mapping[str, Any]: ...


class NoProfile:
    """Until feature 005 stores the use-case profile, there are no use-case values."""

    def values(self, usecase_id: str, run_id: str | None = None) -> Mapping[str, Any]:
        return {}


class ParameterService:
    """Resolves once per run, freezes it in ``run_parameter_set``, and reads it back."""

    def __init__(
        self,
        engine: Engine,
        guardrails: Mapping[str, Any],
        profile: ProfileSource | None = None,
    ) -> None:
        self.engine = engine
        self.guardrails = guardrails
        self.profile = profile or NoProfile()
        self._cache: dict[str, dict[str, Any]] = {}

    def __call__(self, context: EvalContext) -> Answer:
        if context.run_id is None or context.usecase_id is None:
            return NOT_AVAILABLE
        if context.run_id not in self._cache:
            self._cache[context.run_id] = self._frozen(context.run_id, context.usecase_id)
        return Evidence(self._cache[context.run_id], "guardrails")

    def _frozen(self, run_id: str, usecase_id: str) -> dict[str, Any]:
        """The run's frozen parameters; resolved and frozen now when the run has none.

        Freezing is written on its own (``write_independently``): the caller may hold the write
        lock (a decision on the run), and the values are fixed here either way."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT parameters FROM run_parameter_set WHERE run_id = :r"),
                {"r": run_id},
            ).scalar()
            if row is not None:
                return {name: entry["value"] for name, entry in dict(row).items()}
            tier = conn.execute(
                text("SELECT risk_tier FROM usecase WHERE usecase_id = :u"),
                {"u": usecase_id},
            ).scalar()
        resolved = resolve(
            self.guardrails.get("guardrails", []),
            tier,
            _proposals(self.profile.values(usecase_id, run_id)),
        )
        parameters = {
            name: {"value": value, "source": resolved.sources[name]}
            for name, value in resolved.values.items()
        }
        values = {
            "r": run_id,
            "t": resolved.tier,
            "v": str(self.guardrails.get("version", "")),
            "p": json.dumps(parameters, default=str),
            "x": json.dumps([asdict(r) for r in resolved.rejected], default=str),
        }

        def freeze() -> None:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO run_parameter_set (run_id, risk_tier, guardrail_version, "
                        "parameters, rejected) VALUES (:r, :t, :v, :p, :x) "
                        "ON CONFLICT (run_id) DO NOTHING"
                    ),
                    values,
                )

        write_independently(self.engine, freeze)
        return {name: entry["value"] for name, entry in parameters.items()}


def _proposals(values: Mapping[str, Any]) -> dict[str, Any]:
    """Profile values as guardrail proposals: a plain value, or a mapping's ``value`` (005)."""
    return {
        name: value["value"] if isinstance(value, Mapping) and "value" in value else value
        for name, value in values.items()
    }
