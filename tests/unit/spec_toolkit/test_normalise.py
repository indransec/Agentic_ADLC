"""T009: normalised form and content hash (research R-09, FR-023)."""

import re

from ruamel.yaml import YAML

from adlc.spec_toolkit.normalise import content_hash, file_hash, normalise

A = """# comment
terminal:
  metadata: {id: T0, version: "1.0.0"}
  timeline:
    reminder_after: 2d
    max_rework_cycles: 3
"""
B = """terminal:
  timeline: {max_rework_cycles: 3,   reminder_after: 2d}   # trailing
  metadata:
    version: "1.0.0"
    id: T0
"""


def _load(text: str) -> object:
    return YAML(typ="safe").load(text)


def test_formatting_only_changes_keep_the_hash() -> None:
    assert normalise(_load(A)) == normalise(_load(B))
    assert content_hash(_load(A)) == content_hash(_load(B))


def test_hash_format_and_sensitivity() -> None:
    first = content_hash(_load(A))
    assert re.match(r"^sha256:[0-9a-f]{64}$", first)
    assert content_hash(_load(A.replace("3", "4"))) != first


def test_normalised_is_compact_sorted_json() -> None:
    assert normalise({"b": 1, "a": "é"}) == '{"a":"é","b":1}'


def test_file_hash_uses_bytes() -> None:
    assert file_hash("---\nid: x\n---\nBody\n") != file_hash("---\nid: x\n---\nBody \n")
