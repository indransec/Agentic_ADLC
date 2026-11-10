"""TDS Annex B.1 durations used by terminal specs, and the demo time scale (research R-07).

Units: ``h`` hours, ``d`` days, ``w`` weeks, ``m`` months of 30 days. These differ from the
platform setting durations in :mod:`adlc.config.durations`, which reject ``m``.
"""

import re
from datetime import timedelta

_PATTERN = re.compile(r"^(?P<value>[0-9]+)(?P<unit>[hdwm])$")
_UNIT = {
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "m": timedelta(days=30),
}
_SCHEDULES = {"weekly": "7d", "fortnightly": "14d", "monthly": "30d"}


class SpecDurationError(ValueError):
    """A spec duration that is not ``<int><h|d|w|m>``."""


def parse(text: str) -> timedelta:
    match = _PATTERN.match(text)
    if match is None:
        raise SpecDurationError(f"not a TDS duration: {text!r} (expected <int><h|d|w|m>)")
    return int(match["value"]) * _UNIT[match["unit"]]


def parse_optional(text: str | None) -> timedelta | None:
    """Duration, or ``None`` for non-duration timeline values (``window_end``, ``continuous``)."""
    if text is None or _PATTERN.match(text) is None:
        return None
    return parse(text)


def scaled(value: timedelta, time_scale: float) -> timedelta:
    if time_scale <= 0:
        raise ValueError("time scale must be greater than zero")
    return value * time_scale


def review_interval(schedule: str) -> timedelta:
    """Interval for a continuous terminal's ``review_schedule`` value."""
    return parse(_SCHEDULES.get(schedule, schedule))
