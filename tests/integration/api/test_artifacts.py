"""T020: artifact edits, spreadsheets, attachments, history and downloads through the API (US3;
FR-011 to FR-013)."""

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from tests.support.api import Api, api_for
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

ARTIFACT = "kpis"  # an artifact of the terminal under test; T1 declares it in adlc-specs
NOTE = b"# KPI source\nfinance extract 2026-10"


@pytest.fixture
def small(h: Harness, tmp_path: Path) -> Iterator[Api]:
    """The API with a 64-byte attachment limit."""
    with api_for(h, tmp_path, attachment_max=64) as built:
        yield built


def xlsx(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = ARTIFACT
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def state(api: Api, run: str, role: str = "product_owner") -> dict[str, Any]:
    return dict(api.get(role, f"/runs/{run}").json())


def rows_of(api: Api, run: str) -> list[dict[str, Any]]:
    artifact = next(a for a in state(api, run)["artifacts"] if a["id"] == ARTIFACT)
    return list(artifact["rows"])


def versions(h: Harness, run: str) -> int:
    count = h.sql("SELECT count(*) FROM run.artifact_version WHERE run_id = :r", r=run)
    return int(count[0][0])


def test_edit_creates_a_person_version_and_resets_approvals(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    shown = state(api, run)
    passed = api.post(
        "business_owner",
        f"/runs/{run}/decisions",
        json={"decision": "pass", "expected_version": shown["run"]["version"]},
    )
    assert passed.status_code == 200
    version = state(api, run)["run"]["version"]
    rows = rows_of(api, run)
    rows[0]["target"] = 99
    edited = api.put(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}",
        json={"rows": rows, "expected_version": version},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["changed"] and edited.json()["run"]["controls_pending"]
    after = state(api, run)
    assert after["approvals"] == []  # the business owner's approval no longer counts
    current = next(a for a in after["artifacts"] if a["id"] == ARTIFACT)
    assert current["version"]["producer_type"] == "person"
    h.drain()  # the worker re-runs the controls
    assert not state(api, run)["run"]["controls_pending"]
    history = api.get("sre", f"/runs/{run}/artifacts/{ARTIFACT}/history").json()
    assert len(history) == 2 and history[-1]["producer_type"] == "person"


def test_unchanged_table_makes_no_version(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    before = versions(h, run)
    same = api.put(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}",
        json={"rows": rows_of(api, run), "expected_version": state(api, run)["run"]["version"]},
    )
    assert same.status_code == 200 and same.json()["changed"] is False
    assert versions(h, run) == before


def test_spreadsheet_upload(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    row = {**rows_of(api, run)[0], "baseline": 12}
    fits = api.post(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}/spreadsheet",
        files={
            "file": ("kpis.xlsx", xlsx([list(row), list(row.values())]), "application/octet-stream")
        },
        data={"expected_version": str(state(api, run)["run"]["version"])},
    )
    assert fits.status_code == 200, fits.text
    assert rows_of(api, run)[0]["baseline"] == 12
    refused = api.post(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}/spreadsheet",
        files={"file": ("kpis.xlsx", b"not excel", "application/octet-stream")},
        data={"expected_version": str(state(api, run)["run"]["version"])},
    )
    assert refused.status_code == 422 and "cannot be read" in refused.json()["detail"]


def test_attachments_and_downloads(h: Harness, api: Api) -> None:
    usecase, run = walk_to(h, "T1")
    version = state(api, run)["run"]["version"]
    attached = api.post(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}/attachments",
        files={"file": ("kpi notes.md", NOTE, "text/markdown")},
        data={"expected_version": str(version)},
    )
    assert attached.status_code == 200, attached.text
    artifact = next(a for a in state(api, run)["artifacts"] if a["id"] == ARTIFACT)
    content_hash = artifact["attachments"][0]["content_hash"]
    got = api.get("sre", f"/runs/{run}/attachments/{content_hash}")
    assert got.status_code == 200 and got.content == NOTE
    assert got.headers["content-type"].startswith("text/markdown")
    assert got.headers["content-disposition"] == "attachment; filename*=UTF-8''kpi%20notes.md"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert got.headers["cache-control"] == "private, no-store"
    # Only for attachments of the run named in the path.
    other = f"{usecase}/T0/run-1"
    assert api.get("sre", f"/runs/{other}/attachments/{content_hash}").status_code == 404
    refused = api.post(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}/attachments",
        files={"file": ("tool.exe", b"MZ\x90", "application/x-msdownload")},
        data={"expected_version": str(state(api, run)["run"]["version"])},
    )
    assert refused.status_code == 422 and refused.json()["kind"] == "invalid"


def test_attachment_over_the_size_limit(h: Harness, small: Api) -> None:
    _, run = walk_to(h, "T1")
    refused = small.post(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}/attachments",
        files={"file": ("big.md", b"x" * 65, "text/markdown")},
        data={"expected_version": str(state(small, run)["run"]["version"])},
    )
    assert refused.status_code == 422 and refused.json()["field"] == "file"


def test_only_editors_may_change_artifacts(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    refused = api.put(
        "sre",
        f"/runs/{run}/artifacts/{ARTIFACT}",
        json={"rows": [], "expected_version": state(api, run)["run"]["version"]},
    )
    assert refused.status_code == 403 and refused.json()["kind"] == "not_allowed"


def test_old_versions_change_nothing(h: Harness, api: Api) -> None:
    _, run = walk_to(h, "T1")
    old = state(api, run)["run"]["version"] - 1
    before = versions(h, run)
    rows = rows_of(api, run)
    rows[0]["target"] = 7
    calls = [
        api.put(
            "product_owner",
            f"/runs/{run}/artifacts/{ARTIFACT}",
            json={"rows": rows, "expected_version": old},
        ),
        api.post(
            "product_owner",
            f"/runs/{run}/artifacts/{ARTIFACT}/attachments",
            files={"file": ("n.md", NOTE, "text/markdown")},
            data={"expected_version": str(old)},
        ),
        api.post(
            "product_owner",
            f"/runs/{run}/artifacts/{ARTIFACT}/spreadsheet",
            files={"file": ("k.xlsx", xlsx([list(rows[0]), list(rows[0].values())]), "x")},
            data={"expected_version": str(old)},
        ),
    ]
    assert [c.status_code for c in calls] == [409, 409, 409]
    assert {c.json()["kind"] for c in calls} == {"stale"}
    assert versions(h, run) == before
