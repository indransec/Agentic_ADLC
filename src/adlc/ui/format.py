"""How values read on screen: durations, money, times, KPI values and column names.

Pure functions (no Streamlit), so every page formats the same way.
"""

import re
from datetime import UTC, datetime
from typing import Any

MISSING = "—"
ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
# Words that read better in capitals in a column name
UPPER = {"id": "ID", "usd": "USD", "kpi": "KPI", "sla": "SLA", "url": "URL"}
WORDS = {"usecase": "use case"}


def duration(seconds: float) -> str:
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = [
        f"{days}d" if days else "",
        f"{hours}h" if hours else "",
        f"{minutes}m" if minutes else "",
    ]
    return " ".join(p for p in parts if p) or f"{sec}s"


def money(value: Any) -> str:
    """US dollars; small model costs keep four decimals."""
    if value is None or value == "":
        return MISSING
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"${amount:,.4f}" if abs(amount) < 1 else f"${amount:,.2f}"


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not ISO_TIME.match(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def when(value: Any) -> str:
    """A time as people read it, in UTC: 19 Nov 2026, 14:05 UTC."""
    parsed = parse_time(value)
    if parsed is None:
        return MISSING if value in (None, "") else str(value)
    return parsed.astimezone(UTC).strftime("%-d %b %Y, %H:%M UTC")


def ago(value: Any, now: datetime | None = None) -> str:
    """How long ago (or how far ahead) a time is: 5m ago, in 2h."""
    parsed = parse_time(value)
    if parsed is None:
        return MISSING
    seconds = ((now or datetime.now(UTC)) - parsed).total_seconds()
    if abs(seconds) < 60:
        return "just now"
    return f"{duration(abs(seconds))} ago" if seconds > 0 else f"in {duration(-seconds)}"


def kpi_value(kpi: dict[str, Any]) -> str:
    value = kpi.get("value")
    if value is None:
        return "no data"
    unit = kpi.get("unit")
    if unit == "ratio":
        return f"{value * 100:.0f}%"
    if unit == "seconds":
        return duration(value)
    return str(value)


def label(key: str) -> str:
    """A column name for people: ``usecase_id`` reads "Use case ID"."""
    words = []
    for word in str(key).replace("_", " ").split():
        lower = word.lower()
        words.append(UPPER.get(lower) or WORDS.get(lower) or word)
    text = " ".join(words)
    return text[:1].upper() + text[1:] if text else text
