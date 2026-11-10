"""T008: resolving a spec's ledger.bound_to in a use case (FR-003)."""

from typing import Any

from adlc.ledger.binding import bound_reference, resolve_bound_to


def _spec(bound: str | None) -> dict[str, Any]:
    ledger: dict[str, Any] = {"key": "${usecase_id}/X/${run_version}"}
    if bound:
        ledger["bound_to"] = bound
    return {"terminal": {"evidence": {"ledger": ledger}}}


def test_reference() -> None:
    assert bound_reference(_spec("T3.candidate_package.sha256")) == (
        "T3",
        ("candidate_package", "sha256"),
    )
    assert bound_reference(_spec(None)) is None
    assert bound_reference(_spec("release.package_sha256")) is None


def test_resolve() -> None:
    records = {"T3": {"candidate_package": [{"sha256": "sha256:abc", "package_uri": "u"}]}}
    assert resolve_bound_to(_spec("T3.candidate_package.sha256"), records.get) == "sha256:abc"
    assert resolve_bound_to(_spec(None), records.get) is None
    assert resolve_bound_to(_spec("T3.missing.sha256"), records.get) is None
    assert resolve_bound_to(_spec("T5.candidate_package.sha256"), records.get) is None
