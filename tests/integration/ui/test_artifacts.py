"""T021: artifact editing, uploads, attachments and downloads in the web application (US3).

AppTest cannot drive ``st.data_editor``, so these tests replace it with a function that returns the
table with one change, which exercises the page's save path through the real API.
"""

from typing import Any

import pytest
import streamlit
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import DownloadButton

from tests.support.api import Api
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness
from tests.support.ui import go, open_ui, sign_in, texts

ARTIFACT = "kpis"  # an artifact of the terminal under test; T1 declares it in adlc-specs
NOTE = b"# KPI source: finance extract 2026-10"


@pytest.fixture
def editors(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the data editor: record its keys, change the first target of the table."""
    seen: list[str] = []

    def fake(data: list[dict[str, Any]], **kw: Any) -> list[dict[str, Any]]:
        seen.append(str(kw["key"]))
        if not str(kw["key"]).endswith(f":{ARTIFACT}"):
            return data
        return [{**data[0], "target": 99}, *data[1:]]

    monkeypatch.setattr(streamlit, "data_editor", fake)
    return seen


def run_page(api: Api, role: str, run: str) -> AppTest:
    at = sign_in(open_ui(api), role)
    at.session_state["run_id"] = run
    at = go(at, "Run")
    assert not at.exception, at.exception
    return at


def history(api: Api, run: str) -> list[Any]:
    return list(api.get("sre", f"/runs/{run}/artifacts/{ARTIFACT}/history").json())


def test_editor_saves_a_change(h: Harness, api: Api, editors: list[str]) -> None:
    _, run = walk_to(h, "T1")
    at = run_page(api, "product_owner", run)
    assert f"edit:{run}:{ARTIFACT}" in editors
    at.button(key=f"save:{run}:{ARTIFACT}").click()
    at = at.run()
    assert "Saved" in [s.value for s in at.success], [e.value for e in at.error]
    latest = history(api, run)[-1]
    assert latest["producer_type"] == "person" and len(history(api, run)) == 2


def test_read_only_for_non_editors(h: Harness, api: Api, editors: list[str]) -> None:
    _, run = walk_to(h, "T1")
    at = run_page(api, "sre", run)
    assert editors == [] and not at.file_uploader
    assert not [b for b in at.button if b.key and b.key.startswith("save:")]


def test_large_tables_are_read_only_with_upload_offered(
    h: Harness, api: Api, editors: list[str]
) -> None:
    _, run = walk_to(h, "T1")
    shown = api.get("product_owner", f"/runs/{run}").json()
    row = next(a for a in shown["artifacts"] if a["id"] == ARTIFACT)["rows"][0]
    many = [{**row, "kpi_id": f"K{n}"} for n in range(1001)]
    put = api.put(
        "product_owner",
        f"/runs/{run}/artifacts/{ARTIFACT}",
        json={"rows": many, "expected_version": shown["run"]["version"]},
    )
    assert put.status_code == 200
    h.drain()
    at = run_page(api, "product_owner", run)
    assert f"edit:{run}:{ARTIFACT}" not in editors
    assert any("More than 1000 rows" in c.value for c in at.caption)
    assert at.file_uploader(key=f"sheet:{run}:{ARTIFACT}") is not None


def test_attach_and_download_only(h: Harness, api: Api, editors: list[str]) -> None:
    _, run = walk_to(h, "T1")
    at = run_page(api, "product_owner", run)
    at.file_uploader(key=f"file:{run}:{ARTIFACT}").set_value(("notes.md", NOTE, "text/markdown"))
    at = at.run()
    at.button(key=f"attach:{run}:{ARTIFACT}").click()
    at = at.run()
    assert "Attached" in [s.value for s in at.success], [e.value for e in at.error]
    at = at.run()
    labels = [d.label for d in at.get("download_button") if isinstance(d, DownloadButton)]
    assert labels == ["Download"] and "notes.md" in texts(at)
    assert all(NOTE.decode() not in t for t in texts(at))  # offered for download, never shown
    assert all(NOTE.decode() not in m.value for m in at.markdown)
