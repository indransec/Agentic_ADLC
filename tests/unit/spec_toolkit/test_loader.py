"""T007: L1 loading, locations, P-01 and P-02."""

from pathlib import Path

from adlc.spec_toolkit.loader import REQUIRED_CATALOGUES, load_bundle


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _minimal(root: Path) -> None:
    for name in REQUIRED_CATALOGUES:
        _write(root, f"shared/{name}.yaml", f"catalogue: {name}\nversion: '1.0.0'\n{name}: []\n")
    _write(root, "terminals/T0.yaml", "terminal:\n  metadata:\n    id: T0\n    version: '1.0.0'\n")
    _write(root, "checklists/t0.yaml", "checklist: t0\nversion: '1.0.0'\nitems: []\n")
    _write(root, "playbooks/t0-intake.md", "---\nid: PB-T0-01\nversion: '1.0.0'\n---\nBody\n")


def test_loads_all_kinds(tmp_path: Path) -> None:
    _minimal(tmp_path)
    bundle = load_bundle(tmp_path)
    assert list(bundle.terminals) == ["terminals/T0.yaml"]
    assert set(bundle.catalogues) == set(REQUIRED_CATALOGUES)
    assert list(bundle.checklists) == ["checklists/t0.yaml"]
    playbook = bundle.playbooks["playbooks/t0-intake.md"]
    assert playbook.data == {"id": "PB-T0-01", "version": "1.0.0"}
    assert playbook.body == "Body\n"
    assert bundle.findings == []


def test_location_index(tmp_path: Path) -> None:
    _minimal(tmp_path)
    bundle = load_bundle(tmp_path)
    assert bundle.location("terminals/T0.yaml", "/terminal/metadata/version") == (4, 5)
    assert bundle.location("terminals/T0.yaml", "/does/not/exist") == (None, None)


def test_parse_error_is_p01_with_position(tmp_path: Path) -> None:
    _minimal(tmp_path)
    _write(tmp_path, "terminals/T1.yaml", "terminal:\n  metadata: [\n")
    bundle = load_bundle(tmp_path)
    p01 = [f for f in bundle.findings if f.rule_id == "P-01"]
    assert len(p01) == 1
    assert p01[0].file == "terminals/T1.yaml"
    assert p01[0].line is not None
    assert bundle.terminals["terminals/T1.yaml"].parse_failed


def test_layout_problems_are_p02(tmp_path: Path) -> None:
    _minimal(tmp_path)
    (tmp_path / "shared" / "predicates.yaml").unlink()
    _write(tmp_path, "terminals/t3.yaml", "terminal: {}\n")
    _write(tmp_path, "checklists/T0-list.yaml", "checklist: x\n")
    bundle = load_bundle(tmp_path)
    messages = [f.message for f in bundle.findings if f.rule_id == "P-02"]
    assert any("shared/predicates.yaml" in m for m in messages)
    assert any("terminals/t3.yaml" in m for m in messages)
    assert any("checklists/T0-list.yaml" in m for m in messages)


def test_catalogue_name_must_match_file(tmp_path: Path) -> None:
    _minimal(tmp_path)
    _write(tmp_path, "shared/metrics.yaml", "catalogue: metric\nversion: '1.0.0'\nmetrics: []\n")
    bundle = load_bundle(tmp_path)
    assert any(f.rule_id == "P-02" and "metrics.yaml" in f.file for f in bundle.findings)
