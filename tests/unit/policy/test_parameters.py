"""T032: parameter resolution against the real guardrails (FR-012 to FR-014, SC-005)."""

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from adlc.policy.parameters import resolve
from adlc.policy.values import as_number

TIERS = ("low", "medium", "high")


@pytest.fixture(scope="module")
def guardrails(registry: Any) -> list[dict[str, Any]]:
    return list(registry.catalogue("guardrails").content["guardrails"])


def _stricter(g: dict[str, Any], tier: str) -> Any:
    value = g["values"][tier]
    if g["direction"] == "superset":
        return [*value, "extra_class"]
    return (
        value - (value * 0.5 if isinstance(value, float) else 1)
        if g["direction"] == "max"
        else value + 1
    )


def _looser(g: dict[str, Any], tier: str) -> Any:
    value = g["values"][tier]
    if g["direction"] == "superset":
        return value[1:]
    return value * 2 + 1 if g["direction"] == "max" else value - 1


@pytest.mark.parametrize("tier", TIERS)
def test_every_real_guardrail_at_every_tier(guardrails: list[dict[str, Any]], tier: str) -> None:
    assert len(guardrails) == 9
    for g in guardrails:
        name, tier_value = g["name"], g["values"][tier]
        absent = resolve(guardrails, tier, {})
        assert (absent.values[name], absent.sources[name]) == (tier_value, "guardrail")
        equal = resolve(guardrails, tier, {name: tier_value})
        assert (equal.values[name], equal.sources[name]) == (tier_value, "usecase")
        stricter = resolve(guardrails, tier, {name: _stricter(g, tier)})
        assert stricter.sources[name] == "usecase", name
        looser = resolve(guardrails, tier, {name: _looser(g, tier)})
        assert (looser.values[name], looser.sources[name]) == (tier_value, "guardrail"), name
        assert looser.rejected[0].name == name and looser.rejected[0].reason


def test_non_numeric_and_missing_tier(guardrails: list[dict[str, Any]]) -> None:
    rejected = resolve(guardrails, "high", {"unit_coverage_min": "eighty"}).rejected
    assert rejected[0].reason == "not numeric"
    assert resolve(guardrails, None, {}).tier == "medium"
    odd = [{"name": "x", "direction": "max", "values": {"low": 1}}]
    assert resolve(odd, "high", {}).unresolved == ("x",)


@given(st.sampled_from(TIERS), st.floats(min_value=-1000, max_value=1000, allow_nan=False))
def test_never_looser_than_the_tier(tier: str, proposed: float) -> None:
    for direction in ("max", "min"):
        g = [
            {
                "name": "p",
                "direction": direction,
                "tighten_only": True,
                "values": {t: 10 for t in TIERS},
            }
        ]
        value = as_number(resolve(g, tier, {"p": proposed}).values["p"])
        assert value is not None
        assert (value <= 10) if direction == "max" else (value >= 10)
