"""Traceability report (feature 014, FR-008, research R-07; SA §21: every decision traceable in
the ledger to spec version, actor and evidence hash).

For one use case, every sign-off, control decision, routing event and artifact version is linked
to the spec version of its run, the actor, and an evidence hash: the run's ledger record hash for
decisions on a closed run (the record holds the artifacts, checks and sign-offs it was decided on),
the hash of the inputs a control read, or the artifact's content hash. A missing link is a gap.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text

KINDS = ("sign_off", "control", "event", "artifact")


@dataclass(frozen=True)
class TraceItem:
    kind: str
    ref: str
    spec_version: str | None
    actor: str | None
    hash: str | None


def _sha(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def gaps(items: Sequence[TraceItem]) -> list[dict[str, Any]]:
    found = []
    for item in items:
        missing = [
            name
            for name, value in (
                ("spec_version", item.spec_version),
                ("actor", item.actor),
                ("hash", item.hash),
            )
            if not value
        ]
        if missing:
            found.append({"kind": item.kind, "ref": item.ref, "missing": missing})
    return found


def items(conn: Connection, usecase_id: str) -> list[TraceItem]:
    runs = {
        str(r["run_id"]): r
        for r in conn.execute(
            text(
                "SELECT r.run_id, r.spec_version, l.content_hash FROM run.terminal_run r "
                "LEFT JOIN ledger.ledger_record l ON l.run_id = r.run_id WHERE r.usecase_id = :u"
            ),
            {"u": usecase_id},
        ).mappings()
    }

    def version(run_id: Any) -> str | None:
        run = runs.get(str(run_id))
        return str(run["spec_version"]) if run else None

    def record(run_id: Any) -> str | None:
        run = runs.get(str(run_id))
        return str(run["content_hash"]) if run and run["content_hash"] else None

    found: list[TraceItem] = []
    for r in conn.execute(
        text(
            "SELECT s.sign_off_id, s.run_id, s.person FROM run.sign_off s JOIN run.terminal_run r "
            "USING (run_id) WHERE r.usecase_id = :u"
        ),
        {"u": usecase_id},
    ).mappings():
        found.append(
            TraceItem(
                "sign_off",
                f"{r['run_id']}#{r['sign_off_id']}",
                version(r["run_id"]),
                str(r["person"]),
                record(r["run_id"]),
            )
        )
    for r in conn.execute(
        text(
            "SELECT policy_decision_id, run_id, check_id, actor, inputs FROM run.policy_decision "
            "WHERE usecase_id = :u AND kind = 'evaluate' AND check_id LIKE 'CTL-%'"
        ),
        {"u": usecase_id},
    ).mappings():
        found.append(
            TraceItem(
                "control",
                f"{r['run_id']}#{r['check_id']}@{r['policy_decision_id']}",
                version(r["run_id"]),
                str(r["actor"] or "policy engine"),
                _sha(r["inputs"]),
            )
        )
    for r in conn.execute(
        text(
            "SELECT event_id, event_type, causation_run_id, payload FROM events.outbox_event "
            "WHERE usecase_id = :u AND causation_run_id IS NOT NULL"
        ),
        {"u": usecase_id},
    ).mappings():
        payload = dict(r["payload"] or {})
        actor = (
            payload.get("raised_by") or payload.get("decided_by") or f"run {r['causation_run_id']}"
        )
        found.append(
            TraceItem(
                "event",
                f"{r['event_type']}#{r['event_id']}",
                version(r["causation_run_id"]),
                str(actor),
                record(r["causation_run_id"]) or _sha(payload),
            )
        )
    for r in conn.execute(
        text(
            "SELECT run_id, artifact_id, version, producer_type, producer_id, content_hash "
            "FROM run.artifact_version WHERE run_id = ANY(:r)"
        ),
        {"r": list(runs)},
    ).mappings():
        found.append(
            TraceItem(
                "artifact",
                f"{r['run_id']}#{r['artifact_id']}@{r['version']}",
                version(r["run_id"]),
                f"{r['producer_type']}:{r['producer_id']}",
                str(r["content_hash"]),
            )
        )
    return found


def trace(conn: Connection, usecase_id: str) -> dict[str, Any]:
    found = items(conn, usecase_id)
    missing = gaps(found)
    return {
        "usecase_id": usecase_id,
        "counts": {k: sum(1 for i in found if i.kind == k) for k in KINDS},
        "gaps": missing,
        "traceable": 1.0 if not found else (len(found) - len(missing)) / len(found),
    }
