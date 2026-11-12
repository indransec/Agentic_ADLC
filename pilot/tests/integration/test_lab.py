"""010 T018: pilot-lab builds a fill exactly as pilot-build does, names a failing fill part, serves
manifests and reproducible datasets with content hashes."""

from pathlib import Path

from fastapi.testclient import TestClient

from pilot_tools.build import build
from pilot_tools.lab import create_lab, layout
from tests.conftest import DEFAULT_FILL, TEMPLATE

DATASETS = Path(__file__).resolve().parents[2] / "datasets.yaml"


def fill_files(folder: Path = DEFAULT_FILL) -> dict[str, str]:
    return {name: (folder / name).read_text() for name in layout(TEMPLATE)}


def test_layout_is_the_templates_fill_points(tmp_path: Path) -> None:
    lab = TestClient(create_lab(TEMPLATE, tmp_path, DATASETS))
    body = lab.get("/layout").json()
    assert body["files"] == sorted(p.name for p in DEFAULT_FILL.iterdir() if p.is_file())
    assert body["template_id"] == "incident-triage"


def test_build_matches_pilot_build_and_passes_every_check(tmp_path: Path) -> None:
    lab = TestClient(create_lab(TEMPLATE, tmp_path / "registry", DATASETS))
    reply = lab.post("/build", json={"files": fill_files()}).json()
    expected = build(TEMPLATE, DEFAULT_FILL, tmp_path / "own").package_hash
    assert reply["package_hash"] == expected
    assert [(c["name"], c["passed"]) for c in reply["checks"]] == [
        ("validate", True),
        ("build", True),
        ("reproducible", True),
        ("smoke", True),
    ]
    manifest = lab.get(f"/packages/{expected}").json()
    assert manifest["package_hash"] == expected
    assert lab.get("/packages/sha256:" + "0" * 64).status_code == 404
    assert lab.get("/packages/not-a-hash").status_code == 404


def test_invalid_fill_names_the_part_and_foreign_files_are_refused(tmp_path: Path) -> None:
    lab = TestClient(create_lab(TEMPLATE, tmp_path, DATASETS))
    files = fill_files()
    files["settings.yaml"] = "token_budget: 999999\nmodel_mode: simulated\n"
    reply = lab.post("/build", json={"files": files}).json()
    assert reply["checks"][0]["name"] == "validate" and not reply["checks"][0]["passed"]
    assert "settings" in reply["checks"][0]["detail"] and "package_hash" not in reply
    assert lab.post("/build", json={"files": {"../etc/passwd": "x"}}).status_code == 422


def test_datasets_are_reproducible_with_hashes(tmp_path: Path) -> None:
    first = TestClient(create_lab(TEMPLATE, tmp_path, DATASETS))
    second = TestClient(create_lab(TEMPLATE, tmp_path, DATASETS))
    listed = {d["id"]: d for d in first.get("/datasets").json()}
    assert set(listed) == {"golden", "regression", "pii"}
    assert listed["golden"]["size"] == 200 and listed["golden"]["sha256"].startswith("sha256:")
    golden = first.get("/datasets/golden").json()
    assert golden == second.get("/datasets/golden").json()
    assert len(golden["rows"]) == 200 and all("expected" in r for r in golden["rows"])
    pii = first.get("/datasets/pii").json()["rows"]
    assert all(r["planted_pii"] for r in pii)
    assert first.get("/datasets/nope").status_code == 404
