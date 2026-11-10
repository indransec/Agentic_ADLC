"""T005: value conventions (contracts/evidence.md)."""

from datetime import timedelta

import pytest
from celpy import celtypes

from adlc.policy import values as v


@pytest.mark.parametrize("value", [{"a": [1, "x", True, None]}, [1.5, {"b": "c"}], "t", 3, False])
def test_round_trip(value: object) -> None:
    assert v.to_py(v.to_cel(value)) == value


@pytest.mark.parametrize(
    ("value", "expected"), [(3, 3.0), ("80", 80.0), (" 0.02 ", 0.02), (2.5, 2.5)]
)
def test_numeric(value: object, expected: float) -> None:
    assert v.as_number(value) == expected
    assert v.is_numeric(value)


@pytest.mark.parametrize("value", ["80%", "n/a", "", None, True, [1]])
def test_not_numeric(value: object) -> None:
    assert not v.is_numeric(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        ("true", True),
        ("YES", True),
        ("1", True),
        ("no", False),
        (False, False),
        (1, False),
        (None, False),
    ],
)
def test_truthy(value: object, expected: bool) -> None:
    assert v.is_truthy(value) is expected


def test_open_rows() -> None:
    assert v.is_open_row({"status": "Open"})
    assert v.is_open_row({"closed": ""})
    assert not v.is_open_row({"closed": "2026-11-01"})
    assert not v.is_open_row({"status": "resolved"})


def test_durations() -> None:
    assert v.to_duration("7d") == celtypes.DurationType(seconds=7 * 86400)
    assert v.to_duration(timedelta(hours=1)) == celtypes.DurationType(seconds=3600)
    assert v.to_duration("window_end") == "window_end"
    assert v.to_py(v.to_duration("2h")) == timedelta(hours=2)


def test_not_available_sentinel() -> None:
    assert v.NOT_AVAILABLE is type(v.NOT_AVAILABLE)()
    assert not v.NOT_AVAILABLE
    assert repr(v.NOT_AVAILABLE) == "NOT_AVAILABLE"
