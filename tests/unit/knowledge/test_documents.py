"""T006: knowledge documents, sections, hashes, and keyword search (research R-06, R-07)."""

import hashlib
from pathlib import Path

from adlc.knowledge.documents import load_folder
from adlc.knowledge.search import MAX_LIMIT, SNIPPET_MAX, Index, read_section

CLASSES = {"public": 0, "internal": 1, "confidential": 2}

POLICY = """---
title: AI use policy
data_class: internal
synthetic: true
collections: [policies]
version: "1.0.0"
---
# AI use policy

Intro text for the whole policy.

## Scope

Applies to every agent that reads customer claims.

## Controls

### Human oversight

A person approves any payout above the threshold.
"""


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_front_matter_sections_and_hashes(tmp_path: Path) -> None:
    write(tmp_path, "sharepoint/policies/ai-use.md", POLICY)
    (doc,) = load_folder(tmp_path, CLASSES)
    assert (doc.source, doc.path, doc.title) == (
        "sharepoint",
        "policies/ai-use.md",
        "AI use policy",
    )
    assert (doc.data_class, doc.synthetic, doc.collections) == ("internal", True, ("policies",))
    assert [s.section for s in doc.sections] == [
        "",
        "Scope",
        "Controls",
        "Controls > Human oversight",
    ]
    oversight = doc.sections[-1]
    assert "payout above the threshold" in oversight.text
    expected = "sha256:" + hashlib.sha256(oversight.text.encode()).hexdigest()
    assert oversight.content_hash == expected


def test_documents_without_a_valid_class_are_never_loaded(tmp_path: Path) -> None:
    write(tmp_path, "confluence/a.md", POLICY.replace("data_class: internal\n", ""))
    write(tmp_path, "confluence/b.md", POLICY.replace("internal", "secret-ish"))
    write(tmp_path, "confluence/c.md", "# no front matter at all\n")
    write(tmp_path, "confluence/ok.md", POLICY)
    assert [d.path for d in load_folder(tmp_path, CLASSES)] == ["ok.md"]


def test_bm25_ranks_the_matching_section_first(tmp_path: Path) -> None:
    write(tmp_path, "sharepoint/policies/ai-use.md", POLICY)
    write(
        tmp_path,
        "sharepoint/policies/travel.md",
        POLICY.replace("payout above the threshold", "hotel booking rules"),
    )
    index = Index(load_folder(tmp_path, CLASSES))
    hits = index.search("payout threshold", lambda doc: True, limit=5)
    assert hits[0].document.path == "policies/ai-use.md"
    assert hits[0].section.section == "Controls > Human oversight"
    assert index.search("nothing matches this", lambda doc: True, limit=5) == []
    assert all(len(h.snippet) <= SNIPPET_MAX for h in hits)


def test_limit_is_capped(tmp_path: Path) -> None:
    for n in range(15):
        write(tmp_path, f"jira/epic-{n}.md", POLICY.replace("AI use policy", f"Epic {n} claims"))
    index = Index(load_folder(tmp_path, CLASSES))
    assert len(index.search("claims", lambda doc: True, limit=50)) == MAX_LIMIT


def test_read_section_and_outline(tmp_path: Path) -> None:
    long = POLICY + "\n## Annex\n\n" + "x" * 9000 + "\n"
    write(tmp_path, "sharepoint/policies/ai-use.md", long)
    (doc,) = load_folder(tmp_path, CLASSES)
    outline = read_section(doc, None)
    assert outline is not None
    assert outline.cut is False and "Controls > Human oversight" in outline.text
    annex = read_section(doc, "Annex")
    assert annex is not None
    assert annex.cut is True and len(annex.text) == 8000
    assert read_section(doc, "Missing") is None
