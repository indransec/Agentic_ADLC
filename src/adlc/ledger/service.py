"""Ledger service operations (contracts/artifacts.md, verification.md; FR-010 to FR-012, FR-019).

Feature 007 exposes these over HTTP. An edit commits the person's version with the
``artifact_edited`` signal: approvals reset, a pending waiver withdrawn, the run's version
bumped and, at sign-off, ``controls_pending`` set. The orchestrator worker then re-runs the
automated controls on the committed content (``controls_rechecked``); until it has, a pass or
exception decision is refused, and a re-check lost to a crash is simply picked up again.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from adlc.ledger import artifacts as versions
from adlc.ledger import store as ledger_store
from adlc.ledger import views
from adlc.ledger.spreadsheet import read_rows
from adlc.ledger.storage import FileRef, LedgerContentStore
from adlc.ledger.verify import Report, Verifier
from adlc.orchestration import spec_view
from adlc.orchestration import store as run_store
from adlc.orchestration.engine import PostgresTerminalRun, UnknownRun
from adlc.orchestration.service import Actor, NotAuthorised
from adlc.orchestration.states import (
    ActorType,
    InvalidTransition,
    RunState,
    Signal,
    SignalKind,
)
from adlc.orchestration.store import RunRow

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EDITABLE = (RunState.AWAITING_SIGN_OFF, RunState.ESCALATED)


class UnknownArtifact(Exception):
    pass


@dataclass(frozen=True)
class Upload:
    data: bytes
    file_name: str
    media_type: str


class LedgerService:
    def __init__(self, runs: PostgresTerminalRun, content: LedgerContentStore) -> None:
        self.runs = runs
        self.content = content

    # -------------------------------------------------------------- edits

    def edit_artifact(
        self, actor: Actor, run_id: str, artifact_id: str, rows: Any, uploads: Sequence[Upload] = ()
    ) -> RunRow:
        run, _ = self._editable(actor, run_id, artifact_id)
        with self.runs.engine.connect() as conn:
            current = {v["artifact_id"]: v for v in ledger_store.latest_versions(conn, run_id)}
        previous = current.get(artifact_id)
        unchanged = not versions.changed(
            None if previous is None else str(previous["content_hash"]), rows
        )
        if unchanged and not uploads:
            return run  # no new version (FR-010)
        with self.runs.engine.begin() as conn:
            refs = [self.content.put_file(conn, u.data, u.media_type) for u in uploads]
            files = [_file_entry(ref, u.file_name) for ref, u in zip(refs, uploads, strict=True)]
            edited = self.runs.apply_in(
                conn,
                run_id,
                Signal(
                    SignalKind.ARTIFACT_EDITED,
                    ActorType.HUMAN,
                    actor.account_name,
                    {
                        "artifacts": {artifact_id: rows},
                        "attachments": {artifact_id: files},
                        # kept on the run's activity record
                        "edited": {
                            "artifact_id": artifact_id,
                            "attachments": [f["name"] for f in files],
                        },
                    },
                ),
                expected_version=run.version,
            )
        return edited  # at sign-off the worker re-runs the controls next (controls_pending)

    def upload_spreadsheet(
        self, actor: Actor, run_id: str, artifact_id: str, data: bytes, file_name: str
    ) -> RunRow:
        rows = read_rows(data, artifact_id)  # InvalidUpload when it does not fit
        return self.edit_artifact(
            actor, run_id, artifact_id, rows, (Upload(data, file_name, XLSX),)
        )

    def attach_file(
        self,
        actor: Actor,
        run_id: str,
        artifact_id: str,
        data: bytes,
        file_name: str,
        media_type: str,
    ) -> RunRow:
        with self.runs.engine.connect() as conn:
            current = versions.current_content(conn, run_id, self.content.get_structured)
        rows = current.get(artifact_id, [])
        return self.edit_artifact(
            actor, run_id, artifact_id, rows, (Upload(data, file_name, media_type),)
        )

    def artifact_history(self, run_id: str, artifact_id: str) -> list[dict[str, Any]]:
        with self.runs.engine.connect() as conn:
            return versions.history(conn, run_id, artifact_id)

    def verify(self, actor: Actor, scope: str = "all") -> Report:
        """Any signed-in person may verify (FR-019); each call is recorded."""
        verifier = Verifier(self.runs.engine, self.runs.registry, self.content.open_file)
        return verifier.verify(scope, actor.account_name)

    def run_view(self, run_id: str) -> dict[str, Any]:
        with self.runs.engine.connect() as conn:
            return views.run_view(conn, run_id)

    def usecase_summary(self, usecase_id: str) -> list[dict[str, Any]]:
        with self.runs.engine.connect() as conn:
            return views.usecase_summary(conn, usecase_id)

    def open_attachment(self, content_hash: str) -> bytes | None:
        """The stored bytes; feature 007 serves them as a download only (FR-012)."""
        return self.content.open_file(content_hash)

    # -------------------------------------------------------------- helpers

    def _editable(
        self, actor: Actor, run_id: str, artifact_id: str
    ) -> tuple[RunRow, Mapping[str, Any]]:
        if actor.kind != "human":
            raise NotAuthorised("only a person can edit an artifact")
        with self.runs.engine.connect() as conn:
            run = run_store.load_run(conn, run_id)
            if run is None:
                raise UnknownRun(run_id)
            spec = self.runs.entry(run.terminal_id, run.spec_version).spec
            ctx = self.runs.context(conn, run)
        if run.state not in EDITABLE:
            raise InvalidTransition(
                f"artifacts can be edited at sign-off or escalation, not in {run.state}"
            )
        if artifact_id not in {a.id for a in spec_view.artifacts(spec)}:
            raise UnknownArtifact(f"{artifact_id} is not an artifact of {run.terminal_id}")
        allowed = ctx.rule_roles | ctx.required_plus_roles | spec_view.accountable_roles(spec)
        if not actor.roles & allowed:
            raise NotAuthorised(f"editing needs one of {sorted(allowed)}")
        return run, spec


def _file_entry(ref: FileRef, name: str) -> dict[str, Any]:
    return {
        "content_hash": ref.content_hash,
        "size": ref.size,
        "media_type": ref.media_type,
        "name": name,
    }
