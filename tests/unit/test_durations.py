from datetime import timedelta

import pytest

from adlc.config.durations import DurationError, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8h", timedelta(hours=8)),
        ("90s", timedelta(seconds=90)),
        ("30min", timedelta(minutes=30)),
        ("7d", timedelta(days=7)),
        ("0s", timedelta(0)),
    ],
)
def test_valid_durations(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["5m", "10", "-1h", "1.5h", "h", "", "8 h", "8H", "2w"])
def test_invalid_durations(text: str) -> None:
    with pytest.raises(DurationError):
        parse_duration(text)


def test_timedelta_passthrough() -> None:
    assert parse_duration(timedelta(seconds=3)) == timedelta(seconds=3)
