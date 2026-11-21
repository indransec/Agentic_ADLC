"""FR-023, constitution XI: no field value, comment, answer or token in any log line or span
(T059a)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adlc.engagement.model import ItemWrite
from adlc.engagement.reconcile import Reconciler
from tests.support.board import Rig, needed_roles
from tests.support.lifecycle import walk_to
from tests.support.orchestration import DEADLETTER_ROLE, Harness, person

MARKERS = (
    "MARK-COMMENT-a1",
    "MARK-REASON-b2",
    "MARK-ANSWER-c3",
    "MARK-INPUT-d4",
    "MARK-STRANGER-e5",
)


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    monkeypatch.setattr(trace, "get_tracer", lambda *a, **k: provider.get_tracer("t"))
    yield memory
    provider.shutdown()


def test_no_marker_reaches_logs_or_spans(
    h: Harness, spans: InMemorySpanExporter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    rig = Rig(h)
    _, run_id = walk_to(h, "T1")
    rig.cycle()
    item = rig.item("run", run_id)
    m = rig.mapping
    approver = needed_roles(h, run_id)[0]
    rig.as_role(approver).update(
        item,
        ItemWrite(
            set={
                m.decision_field: m.value_for("rework"),
                m.comment_field: MARKERS[0],
                m.inputs()["reason"].field: MARKERS[1],
                m.inputs()["root_cause"].field: MARKERS[3],
            }
        ),
    )  # refused: an unknown root cause, whose value the refusal names on the board only
    rig.cycle()
    rig.board.as_user(f"{MARKERS[4].lower()}@board.test").update(
        item, ItemWrite(set={m.decision_field: MARKERS[2]})
    )
    rig.cycle()
    Reconciler(h.app, rig.projector, rig.board, m, h.clock, DEADLETTER_ROLE).reconcile(
        person(DEADLETTER_ROLE)
    )
    logged = caplog.text
    recorded = " ".join(
        f"{s.name} {dict(s.attributes or {})} {[e.attributes for e in s.events]}"
        for s in spans.get_finished_spans()
    )
    assert spans.get_finished_spans(), "the engagement layer writes spans"
    for marker in MARKERS:
        assert marker not in logged, marker
        assert marker not in recorded, marker
    reasons = " ".join(
        str(r[0]) for r in h.sql("SELECT reason FROM inbound_outcome WHERE reason IS NOT NULL")
    )
    assert MARKERS[0] not in reasons and MARKERS[1] not in reasons
