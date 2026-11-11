"""T009: each operation's span names the account, run and use case, never the body (FR-023,
research R-10)."""

from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tests.support.api import api_for
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

SECRET_COMMENT = "body-text-that-must-not-reach-a-span"


@pytest.fixture(autouse=True)
def _enable_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)  # tests disable it by default


def test_spans_carry_account_run_and_use_case(h: Harness, tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    with api_for(h, tmp_path, exporter) as api:
        usecase, run = walk_to(h, "T1")
        api.get("product_owner", f"/usecases/{usecase}")
        version = api.get("product_owner", f"/runs/{run}").json()["run"]["version"]
        api.post(
            "product_owner",
            f"/runs/{run}/decisions",
            json={"decision": "terminate", "comment": SECRET_COMMENT, "expected_version": version},
        )
        api.app.state.tracer_provider.force_flush()
    attributes = [dict(s.attributes or {}) for s in exporter.get_finished_spans()]
    assert any(
        a.get("account") == "product_owner-person" and a.get("run_id") == run for a in attributes
    )
    assert any(a.get("usecase_id") == usecase for a in attributes)
    assert all(SECRET_COMMENT not in str(v) for a in attributes for v in a.values())
