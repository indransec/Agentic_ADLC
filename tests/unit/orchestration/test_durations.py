"""T009: TDS Annex B.1 durations (h, d, w, m = 30 days) with the demo time scale."""

from datetime import timedelta

import pytest

from adlc.orchestration import durations


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("72h", timedelta(hours=72)),
        ("7d", timedelta(days=7)),
        ("2w", timedelta(weeks=2)),
        ("12m", timedelta(days=360)),
    ],
)
def test_parse(text: str, expected: timedelta) -> None:
    assert durations.parse(text) == expected


@pytest.mark.parametrize("text", ["", "7", "7 d", "7y", "-1d", "1.5d", "window_end"])
def test_parse_rejects(text: str) -> None:
    with pytest.raises(durations.SpecDurationError, match=repr(text)):
        durations.parse(text)


def test_optional_returns_none_for_non_durations() -> None:
    assert durations.parse_optional("window_end") is None
    assert durations.parse_optional("continuous") is None
    assert durations.parse_optional(None) is None
    assert durations.parse_optional("2d") == timedelta(days=2)


def test_scaled() -> None:
    assert durations.scaled(timedelta(days=7), 0.0001) == timedelta(seconds=60.48)
    assert durations.scaled(timedelta(hours=1), 1.0) == timedelta(hours=1)
    with pytest.raises(ValueError):
        durations.scaled(timedelta(hours=1), 0)


@pytest.mark.parametrize(
    ("schedule", "days"), [("weekly", 7), ("fortnightly", 14), ("monthly", 30), ("3d", 3)]
)
def test_review_schedule(schedule: str, days: int) -> None:
    assert durations.review_interval(schedule) == timedelta(days=days)
