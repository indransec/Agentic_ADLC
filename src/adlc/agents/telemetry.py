"""Span attributes for the agent runtime: an allow list, short values only (006 FR-023).

Spans never carry prompt text, model output or artifact content. Only the attributes listed here
are set, and every string value is cut to ``MAX_VALUE`` characters.
"""

from collections.abc import Mapping
from typing import Any

from opentelemetry.trace import Span

MAX_VALUE = 200
ALLOWED = frozenset(
    {
        "run_id",
        "usecase_id",
        "terminal_id",
        "agent_id",
        "agent_version",
        "attempt",
        "kind",
        "implementation",
        "tier",
        "provider",
        "model",
        "entry_index",
        "tokens_in",
        "tokens_out",
        "cost_usd",
        "cost_known",
        "outcome",
        "reason",
        "fallback",
        "steps",
        "corrections",
        "limit_reached",
        "latency_ms",
    }
)


def set_attributes(span: Span, values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        if key not in ALLOWED or value is None:
            continue
        if isinstance(value, bool | int | float):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, str(value)[:MAX_VALUE])
