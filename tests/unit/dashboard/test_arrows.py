"""013 T003 (research R-02, analysis A1): arrow kinds from the routing event and terminals."""

import pytest

from adlc.dashboard.journey import arrow_kind, terminal_order


@pytest.mark.parametrize(
    ("event", "source", "target", "kind"),
    [
        ("T4.rework.defect", "T4", "T4", "rework"),
        ("T4.rework", "T4", "T4", "rework"),
        ("T4.rework.defect", "T4", "T3", "reroute"),  # earlier terminal, still a reroute
        ("T5.exception", "T5", "T6", "exception"),
        ("T8.event.drift", "T8", "T9", "event"),
        ("T9.reentry.T2", "T9", "T2", "re-entry"),
        ("T9.pass", "T9", "T2", "re-entry"),  # a pass to an earlier terminal
        ("T3.pass", "T3", "T4", "pass"),
        ("T8.terminate", "T8", "T9", "terminate"),
        ("T2.escalate", "T2", "T2", "escalate"),
    ],
)
def test_kinds(event: str, source: str, target: str, kind: str) -> None:
    assert arrow_kind(event, source, target) == kind


def test_terminals_ordered_by_number() -> None:
    assert sorted(["T10", "T2", "T0", "T9"], key=terminal_order) == ["T0", "T2", "T9", "T10"]
