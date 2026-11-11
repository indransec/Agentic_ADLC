"""T008: citations are optional and must match a retrieval of the same attempt; the addressee
is a terminal role (008 FR-016, FR-017; contracts/agent-output.md)."""

import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

from adlc.agents.knowledge import Retrieval
from adlc.agents.output import parse_builder
from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import Artifacts, Clarification
from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.registry import InMemorySpecRegistry

SPECS = Path(__file__).resolve().parents[3] / "adlc-specs"
HASH = "sha256:" + "b" * 64


@cache
def t0() -> Mapping[str, Any]:
    entry = InMemorySpecRegistry.from_bundle(load_bundle(SPECS)).entry("T0")
    assert entry is not None
    return entry.spec


def full() -> dict[str, list[dict[str, Any]]]:
    return {a.id: [{c: "x" for c in a.columns}] for a in spec_view.artifacts(t0())}


RETRIEVED = [
    Retrieval(
        "sharepoint",
        "search",
        "data",
        "policies/data.md",
        "Claims data",
        HASH,
        "internal",
        True,
        retrieval_id=7,
    )
]


def parse(answer: dict[str, Any], retrieved: list[Retrieval] | None = None) -> Any:
    roles = {r.role for r in spec_view.human_roles(t0())}
    return parse_builder(
        json.dumps(answer), t0(), lambda a: True, roles, retrievals=lambda: retrieved or []
    )


def test_citations_are_optional() -> None:
    parsed = parse({"artifacts": full()})
    assert isinstance(parsed.result, Artifacts) and parsed.result.citations == ()


def test_a_valid_citation_takes_the_hash_from_the_retrieval() -> None:
    cite = {
        "artifact": "data_access",
        "row": 0,
        "source": "sharepoint",
        "document": "policies/data.md",
        "section": "Claims data",
    }
    parsed = parse({"artifacts": full(), "citations": [cite]}, RETRIEVED)
    assert not parsed.problems
    (c,) = parsed.result.citations
    assert (c.artifact, c.row, c.content_hash, c.retrieval_id) == ("data_access", 0, HASH, 7)


def test_invalid_citations_fail() -> None:
    base = {
        "artifact": "data_access",
        "row": 0,
        "source": "sharepoint",
        "document": "policies/data.md",
        "section": "Claims data",
    }
    for wrong in (
        {**base, "document": "never-read.md"},  # not retrieved in this attempt
        {**base, "section": "Other"},
        {**base, "artifact": "not_an_artifact"},
        {**base, "row": 5},  # no such row
        {**base, "content_hash": HASH},  # unknown key
    ):
        parsed = parse({"artifacts": full(), "citations": [wrong]}, RETRIEVED)
        assert parsed.problems and parsed.result is None, wrong
    no_tools = parse({"artifacts": full(), "citations": [base]}, [])
    assert no_tools.problems


def test_no_status_or_other_keys() -> None:
    for extra in ({"status": "pass"}, {"recommendation": "pass"}):
        assert parse({"artifacts": full(), **extra}).problems


def test_addressee_must_be_a_terminal_role() -> None:
    ask = {"questions": ["Who owns the claims data?"], "looked_in": ["sharepoint:/policies"]}
    good = parse({"clarification": {**ask, "addressed_role": "business_owner"}})
    assert isinstance(good.result, Clarification)
    assert parse({"clarification": {**ask, "addressed_role": None}}).result is not None
    assert parse({"clarification": {**ask, "addressed_role": "sre"}}).problems  # not a T0 role
