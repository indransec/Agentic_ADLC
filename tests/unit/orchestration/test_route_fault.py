"""014 T016 (FR-007; research R-06): the test-only route fault fails routing of one event type."""

import pytest

from adlc.config.settings import OrchestratorSettings
from adlc.orchestration.router import RouteFault, route_fault
from adlc.orchestration.store import EventRow


def _event(event_type: str) -> EventRow:
    fields = {name: None for name in EventRow.__dataclass_fields__}
    return EventRow(**{**fields, "event_type": event_type})  # type: ignore[arg-type]


def test_only_the_named_event_type_fails() -> None:
    hook = route_fault("T1.pass")
    with pytest.raises(RouteFault, match="T1.pass"):
        hook(_event("T1.pass"))
    hook(_event("T2.pass"))  # others route normally


def test_unset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADLC_ROUTE_FAULT", raising=False)
    assert OrchestratorSettings.model_fields["route_fault"].default is None
