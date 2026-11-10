"""006: data-class resolvers read the use case's evidence; anything unclear fails closed."""

from typing import Any

from adlc.agents.context import resolve_ceiling
from tests.support.lifecycle import walk_to
from tests.support.orchestration import Harness

CLASSES: dict[str, Any] = {
    "data_classes": [
        {"id": "internal", "rank": 2},
        {"id": "confidential_masked", "rank": 4},
        {"id": "confidential", "rank": 5},
    ],
    "resolvers": [
        {"id": "per_T2_prod_design", "source": "T2.data_strategy.classification"},
        {"id": "unsourced"},
    ],
}


def test_resolver_reads_the_latest_record(h: Harness) -> None:
    usecase, _ = walk_to(h, "T2")
    with h.app.connect() as conn:
        assert resolve_ceiling(conn, usecase, "internal", CLASSES) == "internal"
        # T2 not closed yet: no record, so the resolver stays unresolved (fails closed).
        assert resolve_ceiling(conn, usecase, "per_T2_prod_design", CLASSES) == "per_T2_prod_design"
    h.pass_run(h.active(usecase, "T2").run_id)
    with h.app.connect() as conn:
        assert (
            resolve_ceiling(conn, usecase, "per_T2_prod_design", CLASSES) == "confidential_masked"
        )
        assert resolve_ceiling(conn, usecase, "unsourced", CLASSES) == "unsourced"


def test_unknown_class_in_the_evidence_fails_closed(h: Harness) -> None:
    """A recorded class the catalogue does not know leaves the resolver unresolved.

    (T2's own control rejects unknown classes, so the case is built with a catalogue that
    lacks the recorded class.)"""
    usecase, t3 = walk_to(h, "T3")
    without = {
        **CLASSES,
        "data_classes": [c for c in CLASSES["data_classes"] if c["id"] != "confidential_masked"],
    }
    with h.app.connect() as conn:
        assert resolve_ceiling(conn, usecase, "per_T2_prod_design", without) == "per_T2_prod_design"
        assert (
            resolve_ceiling(conn, usecase, "per_T2_prod_design", CLASSES) == "confidential_masked"
        )
