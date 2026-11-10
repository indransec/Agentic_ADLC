"""T008: runtime identifiers (SA Annex A.5) and time-ordered event ids (RFC 9562 UUID v7)."""

import uuid

import pytest

from adlc.orchestration import ids


def test_usecase_and_waiver_ids() -> None:
    assert ids.usecase_id(1) == "UC-0001"
    assert ids.usecase_id(42) == "UC-0042"
    assert ids.waiver_id(7) == "WVR-0007"
    with pytest.raises(ValueError):
        ids.usecase_id(10000)


def test_run_ids_round_trip() -> None:
    run = ids.run_id("UC-0042", "T3", 2)
    assert run == "UC-0042/T3/run-2"
    assert ids.parse_run_id(run) == ("UC-0042", "T3", 2)
    with pytest.raises(ValueError):
        ids.parse_run_id("UC-42/T3/run-2")


def test_clarification_ids() -> None:
    assert ids.clarification_id("UC-0042/T3/run-2", 1) == "UC-0042/T3/run-2/clar-1"


def test_uuid7_version_and_order() -> None:
    values = [ids.uuid7() for _ in range(2000)]
    assert all(isinstance(v, uuid.UUID) and v.version == 7 for v in values)
    assert all(v.variant == uuid.RFC_4122 for v in values)
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_uuid7_embeds_milliseconds() -> None:
    value = ids.uuid7(unix_ms=1_700_000_000_123)
    assert value.int >> 80 == 1_700_000_000_123
