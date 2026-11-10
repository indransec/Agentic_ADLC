"""Ledger record content, version 2 (contracts/record.md; FR-001, FR-002).

Version 1 is the feature 003 baseline (inline artifacts, no ``content_version`` key); it stays
valid and is verified for hash and chain only (FR-024).
"""

from collections.abc import Mapping, Sequence
from typing import Any

from adlc.spec_toolkit.normalise import content_hash

CONTENT_VERSION = 2


def build_v2(
    *,
    run_id: str,
    usecase_id: str,
    terminal_id: str,
    spec_version: str,
    spec_hash: str,
    trigger: Mapping[str, Any],
    final_status: str,
    decisions: Sequence[Mapping[str, Any]],
    recommendation: Mapping[str, Any] | None,
    control_results: Sequence[Mapping[str, Any]],
    clarifications: Sequence[Mapping[str, Any]],
    waiver: Mapping[str, Any] | None,
    emitted: Mapping[str, Any],
    profile_version: int,
    artifacts: Sequence[Mapping[str, Any]],
    bound_to: Any,
) -> dict[str, Any]:
    return {
        "content_version": CONTENT_VERSION,
        "run_id": run_id,
        "usecase_id": usecase_id,
        "terminal_id": terminal_id,
        "spec": {"version": spec_version, "content_hash": spec_hash},
        "trigger": dict(trigger),
        "final_status": final_status,
        "decisions": [dict(d) for d in decisions],
        "reviewer_recommendation": None if recommendation is None else dict(recommendation),
        "control_results": [dict(c) for c in control_results],
        "clarification_rounds": [dict(c) for c in clarifications],
        "waiver": None if waiver is None else dict(waiver),
        "emitted": dict(emitted),
        "profile_version": profile_version,
        "artifacts": [dict(a) for a in artifacts],
        "bound_to": bound_to,
    }


def content_version(content: Mapping[str, Any]) -> int:
    return int(content.get("content_version", 1))


def record_hash(content: Mapping[str, Any]) -> str:
    return content_hash(content)
