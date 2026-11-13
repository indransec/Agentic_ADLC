"""012 T018 (FR-007): a proposed event's type names the operational event to raise."""

import pytest

from adlc.inbox.proposed_events import event_name


@pytest.mark.parametrize(
    ("given", "name"),
    [
        ("drift", "drift"),
        ("T8.event.cost_overrun", "cost_overrun"),
        (" kpi_shortfall ", "kpi_shortfall"),
    ],
)
def test_event_name(given: str, name: str) -> None:
    assert event_name(given) == name
