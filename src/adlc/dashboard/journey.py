"""Journey building blocks (feature 013, research R-02, R-03): arrow kinds and lane order.

The event type decides first (rework, re-entry, exception, event, terminate, escalate); only a
pass whose target lies before its source is a re-entry (analysis A1). Terminals are ordered by
their number; no terminal is named here.
"""

import re

NUMBER = re.compile(r"(\d+)")


def terminal_order(terminal_id: str) -> tuple[int, str]:
    found = NUMBER.search(terminal_id)
    return (int(found.group(1)) if found else 10**6, terminal_id)


def arrow_kind(event_type: str, source: str, target: str) -> str:
    parts = event_type.split(".")
    status = parts[1] if len(parts) > 1 else ""
    if status == "rework":
        return "rework" if source == target else "reroute"
    if status == "reentry":
        return "re-entry"
    if status in ("exception", "event", "terminate", "escalate"):
        return status
    if terminal_order(target) < terminal_order(source):
        return "re-entry"
    return "pass"
