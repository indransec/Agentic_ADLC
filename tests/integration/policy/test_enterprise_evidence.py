"""T003 (012 research R-04, contracts/telemetry-evidence.md): ``change``, ``release`` and
``retirement`` from the enterprise mocks' records."""

from typing import Any

import pytest
from sqlalchemy import Engine

from adlc.policy import enterprise_evidence
from adlc.tools.enterprise.records import EnterpriseStore
from adlc.tools.token import Claims

UC = "UC-0001"
HASH = "sha256:" + "5a" * 32


def _claims(terminal: str, usecase: str = UC) -> Claims:
    return Claims(f"{usecase}/{terminal}/run-1", usecase, terminal, 1, ())


def _read(engine: Engine, source: str, authorised: str | None = HASH) -> Any:
    with engine.connect() as conn:
        return enterprise_evidence.read(conn, source, UC, lambda: authorised)


@pytest.fixture
def store(app_engine: Engine) -> EnterpriseStore:
    return EnterpriseStore(app_engine)


def _change(store: EnterpriseStore, start: str = "2026-11-12T10:00:00+00:00") -> str:
    body = {
        "summary": "Release",
        "window_start": start,
        "window_end": "2026-11-12T18:00:00+00:00",
        "risk": "low",
        "plan": "canary",
        "state": "new",
    }
    return str(store.add("servicenow", "change", "CHG", _claims("T6"), body)["id"])


def test_nothing_recorded_is_not_available(app_engine: Engine) -> None:
    for source in enterprise_evidence.SOURCES:
        assert _read(app_engine, source, authorised=None) is None


def test_change_from_the_latest_change_record(app_engine: Engine, store: EnterpriseStore) -> None:
    _change(store, "2026-11-10T10:00:00+00:00")
    latest = _change(store)
    found = _read(app_engine, "change")
    assert found == {
        "change_id": latest,
        "window": {"start": "2026-11-12T10:00:00+00:00", "end": "2026-11-12T18:00:00+00:00"},
        "window_requested": True,
        "request_status": "new",
    }
    store.update("servicenow", latest, _claims("T6"), {"state": "approved"})
    assert _read(app_engine, "change")["request_status"] == "approved"


def test_another_use_case_change_is_not_read(app_engine: Engine, store: EnterpriseStore) -> None:
    body = {"window_start": "x", "window_end": "y", "state": "approved"}
    store.add("servicenow", "change", "CHG", _claims("T6", "UC-0002"), body)
    assert _read(app_engine, "change") is None


def test_release_from_the_authorised_package_and_the_window(
    app_engine: Engine, store: EnterpriseStore
) -> None:
    assert _read(app_engine, "release") is None  # no change raised yet: no release
    _change(store)
    assert _read(app_engine, "release") == {"package_sha256": HASH, "release_date": "2026-11-12"}


def test_retirement_reads_revocations_cmdb_and_dependants(
    app_engine: Engine, store: EnterpriseStore
) -> None:
    agent = store.add("agent_registry", "agent", "AG", _claims("T7"), {"name": "a", "owner": "o"})
    store.add("cmdb", "ci", "CI", _claims("T7"), {"name": "a", "data_status": "live"})
    found = _read(app_engine, "retirement")
    assert found == {"credentials_revoked": False, "data_disposed": False, "unowned_dependants": 0}

    for what in ("identity", "tool_scopes"):
        store.add("iam", "revocation", "REV", _claims("T9"), {"what": what, "identities": []})
    ci = store.records("cmdb", UC)[0]["id"]
    store.update("cmdb", ci, _claims("T9"), {"data_status": "disposed"})
    dependant = {"name": "b", "owner": "", "depends_on": str(agent["id"])}
    store.add("agent_registry", "agent", "AG", _claims("T7", "UC-0002"), dependant)
    found = _read(app_engine, "retirement")
    assert found == {"credentials_revoked": True, "data_disposed": True, "unowned_dependants": 1}


def test_one_revocation_is_not_enough(app_engine: Engine, store: EnterpriseStore) -> None:
    store.add("iam", "revocation", "REV", _claims("T9"), {"what": "identity", "identities": []})
    assert _read(app_engine, "retirement")["credentials_revoked"] is False


def test_registry_by_agent_id(app_engine: Engine, store: EnterpriseStore) -> None:
    assert _read(app_engine, "registry") is None
    attributes = {"name": "a", "version": "1.0.0", "owner": "service_owner", "autonomy_level": "2"}
    agent = store.add("agent_registry", "agent", "AG", _claims("T7"), attributes)
    assert _read(app_engine, "registry") == {"agents": {agent["id"]: attributes}}
