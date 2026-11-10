"""Spans around policy, agent, reviewer and routing calls (constitution X; contracts/interfaces.md).

Spans are named ``adlc.<component>.<operation>`` and carry ``run_id``, ``usecase_id`` and
``terminal_id``. The tracer provider is configured by the process (API or orchestrator); without
one, OpenTelemetry's no-op tracer is used.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span

TRACER_NAME = "adlc.orchestration"


@contextmanager
def span(
    component: str,
    operation: str,
    *,
    run_id: str | None = None,
    usecase_id: str | None = None,
    terminal_id: str | None = None,
) -> Iterator[Span]:
    attributes = {
        key: value
        for key, value in (
            ("run_id", run_id),
            ("usecase_id", usecase_id),
            ("terminal_id", terminal_id),
        )
        if value is not None
    }
    tracer = trace.get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(f"adlc.{component}.{operation}", attributes=attributes) as s:
        yield s
