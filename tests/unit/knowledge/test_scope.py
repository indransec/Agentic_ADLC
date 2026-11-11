"""T007: grounding scope items and the data class filter (research R-03)."""

from pathlib import Path

from adlc.knowledge.documents import load_folder
from adlc.knowledge.scope import Scope, class_allowed

CLASSES = {"public": 0, "internal": 1, "confidential": 2}


def doc(tmp_path: Path, rel: str, collections: str = "[]", data_class: str = "internal") -> None:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: t\ndata_class: {data_class}\nsynthetic: true\ncollections: {collections}\n"
        'version: "1.0.0"\n---\n# t\n\nbody\n'
    )


def test_path_prefixes_and_collection_labels(tmp_path: Path) -> None:
    doc(tmp_path, "sharepoint/strategy/plan.md")
    doc(tmp_path, "sharepoint/strategy-old/plan.md")
    doc(tmp_path, "sharepoint/policies/ai.md")
    doc(tmp_path, "sharepoint/finance/budget.md")
    doc(tmp_path, "arch_repo/ra/claims.md", collections="[Reference Architectures]")
    doc(tmp_path, "arch_repo/adr/0001.md", collections="[ADRs]")
    doc(tmp_path, "arch_repo/misc/notes.md")
    docs = {d.source + ":" + d.path: d for d in load_folder(tmp_path, CLASSES)}

    paths = Scope.parse(["/strategy, /policies"])
    assert sorted(k for k, d in docs.items() if paths.contains(d)) == [
        "sharepoint:policies/ai.md",
        "sharepoint:strategy/plan.md",
    ]  # prefix means the folder, not "strategy-old"
    labels = Scope.parse(["reference architectures, ADRs"])
    assert sorted(k for k, d in docs.items() if labels.contains(d)) == [
        "arch_repo:adr/0001.md",
        "arch_repo:ra/claims.md",
    ]


def test_no_grounding_entry_means_nothing_in_scope(tmp_path: Path) -> None:
    doc(tmp_path, "sharepoint/strategy/plan.md")
    (only,) = load_folder(tmp_path, CLASSES)
    assert not Scope.parse([]).contains(only)
    assert not Scope.parse(["", " , "]).contains(only)


def test_data_class_filter_fails_closed() -> None:
    assert class_allowed("internal", "internal", CLASSES)
    assert class_allowed("public", "internal", CLASSES)
    assert not class_allowed("confidential", "internal", CLASSES)
    assert not class_allowed("internal", "unknown-or-resolver", CLASSES)
    assert not class_allowed("internal", "", CLASSES)
