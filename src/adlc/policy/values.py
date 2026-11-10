"""Value conventions shared by the engine and the predicates (contracts/evidence.md).

* "numeric": a number, or text that parses as one (``"80"``, ``" 0.02 "``); ``"80%"`` is not.
* "truthy": ``true`` or the text ``true``, ``yes`` or ``1`` (any case).
* "open row": ``status`` is ``open``, or a ``closed`` column is empty.
"""

import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Final

from celpy import celtypes
from celpy.adapter import json_to_cel

from adlc.orchestration import durations


class _NotAvailable:
    _instance: "_NotAvailable | None" = None

    def __new__(cls) -> "_NotAvailable":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NOT_AVAILABLE"

    def __bool__(self) -> bool:
        return False


NOT_AVAILABLE: Final = _NotAvailable()
TRUTHY_TEXT = frozenset({"true", "yes", "1"})


def to_cel(value: Any) -> Any:
    """Plain Python (JSON-like, plus timedelta/datetime) → CEL values."""
    if isinstance(value, timedelta):
        return celtypes.DurationType(seconds=int(value.total_seconds()))
    if isinstance(value, datetime):
        return celtypes.TimestampType(value)
    if isinstance(value, Mapping):
        return celtypes.MapType({celtypes.StringType(str(k)): to_cel(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return celtypes.ListType([to_cel(v) for v in value])
    if value is None:
        return None
    return json_to_cel(value)


def to_py(value: Any) -> Any:
    """CEL values → plain Python (JSON-like; durations and timestamps as timedelta/datetime)."""
    if isinstance(value, celtypes.BoolType):
        return bool(value)
    if isinstance(value, celtypes.DurationType):
        return timedelta(seconds=float(value.total_seconds()))
    if isinstance(value, celtypes.TimestampType):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if isinstance(value, Mapping):
        return {str(k): to_py(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_py(v) for v in value]
    if isinstance(value, celtypes.IntType | celtypes.UintType):
        return int(value)
    if isinstance(value, celtypes.DoubleType):
        return float(value)
    if isinstance(value, celtypes.StringType):
        return str(value)
    return value


def to_json(value: Any) -> Any:
    """A JSON-safe rendering for decision records."""
    return json.loads(json.dumps(to_py(value), default=str))


def as_number(value: Any) -> float | None:
    value = to_py(value)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def is_numeric(value: Any) -> bool:
    return as_number(value) is not None


def is_truthy(value: Any) -> bool:
    value = to_py(value)
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in TRUTHY_TEXT


def is_empty(value: Any) -> bool:
    value = to_py(value)
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | dict):
        return not value
    return False


def text(value: Any) -> str:
    value = to_py(value)
    return "" if value is None else str(value).strip()


def is_open_row(row: Mapping[str, Any]) -> bool:
    if text(row.get("status")).lower() == "open":
        return True
    return "closed" in row and is_empty(row.get("closed"))


def to_duration(value: str | timedelta | None) -> Any:
    """TDS duration text or a timedelta → CEL duration; other text stays text."""
    if isinstance(value, timedelta):
        return to_cel(value)
    parsed = durations.parse_optional(value)
    return to_cel(parsed) if parsed is not None else (None if value is None else str(value))
