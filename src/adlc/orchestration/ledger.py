"""Baseline ledger record content and hash chain (research R-09; feature 005 extends it).

The content is a plain mapping hashed through the 002 normal form, so formatting never changes
a hash. ``previous_record_hash`` chains the records of one use case.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from adlc.spec_toolkit.normalise import content_hash


@dataclass(frozen=True)
class LedgerRecord:
    ledger_key: str
    run_id: str
    usecase_id: str
    content: Mapping[str, Any]
    content_hash: str
    previous_record_hash: str | None


def build_record_content(
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
    artifacts: Mapping[str, Any],
    control_results: Sequence[Mapping[str, Any]],
    clarifications: Sequence[Mapping[str, Any]],
    waiver: Mapping[str, Any] | None,
    emitted: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "usecase_id": usecase_id,
        "terminal_id": terminal_id,
        "spec": {"version": spec_version, "content_hash": spec_hash},
        "trigger": dict(trigger),
        "final_status": final_status,
        "decisions": [dict(d) for d in decisions],
        "reviewer_recommendation": None if recommendation is None else dict(recommendation),
        "artifacts": dict(artifacts),
        "control_results": [dict(c) for c in control_results],
        "clarification_rounds": [dict(c) for c in clarifications],
        "waiver": None if waiver is None else dict(waiver),
        "emitted": dict(emitted),
    }


def make_record(
    *,
    ledger_key: str,
    content: Mapping[str, Any],
    previous_record_hash: str | None,
) -> LedgerRecord:
    return LedgerRecord(
        ledger_key=ledger_key,
        run_id=str(content["run_id"]),
        usecase_id=str(content["usecase_id"]),
        content=content,
        content_hash=content_hash(content),
        previous_record_hash=previous_record_hash,
    )
