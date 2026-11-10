"""Ledger verification (contracts/verification.md; FR-016 to FR-019; research R-08).

``check_chain`` is pure: it recomputes every record's hash, the chain, and (for version-2 records)
every artifact and attachment hash and the package binding, using lookups passed in. ``Verifier``
reads the records and content, runs the checks, and records the verification run. Reports carry
keys, hashes and names, never artifact content.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from adlc.ledger.binding import bound_reference
from adlc.ledger.content import content_version, record_hash
from adlc.ledger.storage import file_hash, structured_hash
from adlc.orchestration.interfaces import Clock, SystemClock
from adlc.orchestration.tracing import span
from adlc.spec_toolkit.registry import SpecRegistry


@dataclass(frozen=True)
class Break:
    ledger_key: str
    check: str  # content | chain | artifact | attachment | binding
    element: str
    expected: Any
    actual: Any


@dataclass(frozen=True)
class RecordRow:
    ledger_key: str
    usecase_id: str
    content_hash: str
    previous_record_hash: str | None
    content: Mapping[str, Any]


@dataclass
class Report:
    scope: str
    records_checked: int = 0
    breaks: list[Break] = field(default_factory=list)
    # Records outside any use-case chain (no use case, e.g. 001's quickstart row): listed, not
    # verifiable, never silently skipped.
    unscoped: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return not self.breaks

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "records_checked": self.records_checked,
            "verified": self.verified,
            "breaks": [asdict(b) for b in self.breaks],
            "unscoped": list(self.unscoped),
        }


BlobLookup = Callable[[str], Any | None]
FileLookup = Callable[[str], bytes | None]
SpecLookup = Callable[[str, str], Mapping[str, Any] | None]


def check_chain(
    records: Sequence[RecordRow], blob: BlobLookup, file: FileLookup, spec_of: SpecLookup
) -> list[Break]:
    """Checks for one use case's records, in chain order."""
    breaks: list[Break] = []
    previous: RecordRow | None = None
    earlier: list[RecordRow] = []
    for record in records:
        key = record.ledger_key
        actual = record_hash(record.content)
        if actual != record.content_hash:
            breaks.append(Break(key, "content", "record", record.content_hash, actual))
        expected_previous = None if previous is None else previous.content_hash
        if record.previous_record_hash != expected_previous:
            breaks.append(
                Break(
                    key,
                    "chain",
                    "previous_record_hash",
                    expected_previous,
                    record.previous_record_hash,
                )
            )
        if content_version(record.content) >= 2:
            breaks += _artifacts(record, blob, file)
            breaks += _binding(record, earlier, blob, spec_of)
        previous = record
        earlier.append(record)
    return breaks


def _artifacts(record: RecordRow, blob: BlobLookup, file: FileLookup) -> list[Break]:
    breaks = []
    for artifact in record.content.get("artifacts") or []:
        digest = str(artifact.get("content_hash"))
        body = blob(digest)
        actual = None if body is None else structured_hash(body)
        if actual != digest:
            breaks.append(
                Break(record.ledger_key, "artifact", str(artifact.get("id")), digest, actual)
            )
        for attachment in artifact.get("attachments") or []:
            expected = str(attachment.get("content_hash"))
            data = file(expected)
            found = None if data is None else file_hash(data)
            if found != expected:
                element = f"{artifact.get('id')}/{attachment.get('name')}"
                breaks.append(Break(record.ledger_key, "attachment", element, expected, found))
    return breaks


def _binding(
    record: RecordRow, earlier: Sequence[RecordRow], blob: BlobLookup, spec_of: SpecLookup
) -> list[Break]:
    spec_ref = record.content.get("spec") or {}
    spec = spec_of(str(record.content.get("terminal_id")), str(spec_ref.get("version")))
    reference = None if spec is None else bound_reference(spec)
    if reference is None:
        return []
    terminal, path = reference
    bound = [r for r in earlier if r.content.get("terminal_id") == terminal]
    expected = None if not bound else _value_in(bound[-1], path, blob)
    actual = record.content.get("bound_to")
    if expected != actual:
        return [
            Break(record.ledger_key, "binding", f"{terminal}.{'.'.join(path)}", expected, actual)
        ]
    return []


def _value_in(record: RecordRow, path: tuple[str, ...], blob: BlobLookup) -> Any:
    """The bound value from the bound terminal's stored artifact (v2) or inline artifacts (v1)."""
    artifact_id, *rest = path
    if content_version(record.content) >= 2:
        entries = [a for a in record.content.get("artifacts") or [] if a.get("id") == artifact_id]
        value: Any = blob(str(entries[0]["content_hash"])) if entries else None
    else:
        value = (record.content.get("artifacts") or {}).get(artifact_id)
    for member in rest:
        if isinstance(value, list):
            value = value[0] if value and isinstance(value[0], Mapping) else None
        if not isinstance(value, Mapping):
            return None
        value = value.get(member)
    return value


class Verifier:
    def __init__(
        self,
        engine: Engine,
        registry: SpecRegistry,
        file: FileLookup,
        clock: Clock | None = None,
    ) -> None:
        self.engine = engine
        self.registry = registry
        self.file = file
        self.clock = clock or SystemClock()

    def verify(self, scope: str, actor: str) -> Report:
        started = self.clock.now()
        report = Report(scope)
        with (
            span("ledger", "verify", usecase_id=None if scope == "all" else scope),
            self.engine.connect() as conn,
        ):
            rows = conn.execute(
                text(
                    "SELECT ledger_key, usecase_id, content_hash, previous_record_hash, "
                    "content_json FROM ledger.ledger_record WHERE usecase_id IS NOT NULL "
                    "AND (:scope = 'all' OR usecase_id = :scope) "
                    "ORDER BY usecase_id, ledger_record_id"
                ),
                {"scope": scope},
            ).all()
            if scope == "all":
                report.unscoped = [
                    str(k)
                    for k in conn.execute(
                        text(
                            "SELECT ledger_key FROM ledger.ledger_record "
                            "WHERE usecase_id IS NULL ORDER BY ledger_record_id"
                        )
                    ).scalars()
                ]
            blobs: dict[str, Any] = {}

            def blob(digest: str) -> Any | None:
                if digest not in blobs:
                    row = conn.execute(
                        text("SELECT body FROM ledger.content_blob WHERE content_hash = :h"),
                        {"h": digest},
                    ).first()
                    blobs[digest] = None if row is None else row[0]
                return blobs[digest]

            def spec_of(terminal: str, version: str) -> Mapping[str, Any] | None:
                entry = self.registry.entry(terminal, version)
                return None if entry is None else entry.spec

            by_usecase: dict[str, list[RecordRow]] = {}
            for r in rows:
                by_usecase.setdefault(str(r[1]), []).append(
                    RecordRow(str(r[0]), str(r[1]), str(r[2]), r[3], dict(r[4] or {}))
                )
            for records in by_usecase.values():
                report.records_checked += len(records)
                report.breaks += check_chain(records, blob, self.file, spec_of)
        self._record(report, actor, started)
        return report

    def _record(self, report: Report, actor: str, started: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO ledger.verification_run (actor, scope, started_at, finished_at, "
                    "records_checked, breaks, verified) VALUES (:a, :s, :st, :fi, :n, "
                    "CAST(:b AS jsonb), :v)"
                ),
                {
                    "a": actor,
                    "s": report.scope,
                    "st": started,
                    "fi": self.clock.now(),
                    "n": report.records_checked,
                    "b": json.dumps(report.as_dict()["breaks"], default=str),
                    "v": report.verified,
                },
            )
