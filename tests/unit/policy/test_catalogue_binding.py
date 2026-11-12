"""T024: the predicate library equals predicates.yaml exactly (FR-002)."""

from typing import Any

import pytest

from adlc.policy.engine import CatalogueMismatch, CelPolicyEngine
from adlc.policy.evidence import InMemoryEvidenceProvider
from adlc.policy.predicates import check_catalogue, load_all


def test_exact_binding(registry: Any) -> None:
    catalogue = registry.catalogue("predicates").content
    library = load_all()
    assert len(library) == 62
    assert check_catalogue(catalogue, library) == []


def test_mismatch_stops_the_engine(registry: Any) -> None:
    catalogue = registry.catalogue("predicates").content
    library = dict(load_all())
    library.pop("scan_clean")
    library["made_up"] = (lambda: None, 0)
    problems = check_catalogue(catalogue, library)
    assert "missing predicate scan_clean" in problems
    assert "predicate made_up is not in the catalogue" in problems
    with pytest.raises(CatalogueMismatch, match="scan_clean"):
        CelPolicyEngine(InMemoryEvidenceProvider({}), library, predicate_catalogue=catalogue)
