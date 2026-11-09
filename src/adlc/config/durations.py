"""Duration settings in the form ``<int><unit>`` (contracts/settings.md).

Units: ``s`` seconds, ``min`` minutes, ``h`` hours, ``d`` days. A bare ``m`` is rejected
because TDS Annex B.1 uses ``m`` for months.
"""

import re
from datetime import timedelta
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>s|min|h|d)$")
_UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600, "d": 86400}

DURATION_FORM = "<int><unit> with unit s, min, h or d (e.g. 8h, 90s)"


class DurationError(ValueError):
    """Raised when a duration string does not match the documented form."""


def parse_duration(value: str | timedelta) -> timedelta:
    if isinstance(value, timedelta):
        return value
    match = _PATTERN.match(value)
    if match is None:
        raise DurationError(f"expected {DURATION_FORM}")
    return timedelta(seconds=int(match["value"]) * _UNIT_SECONDS[match["unit"]])


def format_duration(value: timedelta) -> str:
    return f"{int(value.total_seconds())}s"


Duration = Annotated[
    timedelta,
    BeforeValidator(parse_duration),
    PlainSerializer(format_duration, return_type=str),
]
