"""Shared wiring for the engagement-layer tests (016): a FakeBoard shaped by the real tracker
mapping, the platform's read side on the orchestration harness, and the projector."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from adlc.config.settings import DEFAULT_ATTACHMENT_TYPES
from adlc.engagement.fake import FakeBoard
from adlc.engagement.mapping import KINDS, TrackerMapping
from adlc.engagement.model import BoardType
from adlc.inbox.service import InboxService
from adlc.ledger.service import LedgerService
from adlc.ledger.storage import FileStore, LedgerContentStore
from tests.support.db import REPO_ROOT

if TYPE_CHECKING:
    from tests.support.api import Api
from tests.support.orchestration import DEADLETTER_ROLE, Harness

MAPPING_FILE = REPO_ROOT / "adlc-specs" / "tracker_mapping.yaml"
SERVICE = "service@board.test"
EVIDENCE = "http://ui.test/run?id="
# A field the mapping neither writes nor reads (a person may change it freely, FR-017).
FREE_FIELD = "System.Tags"


def mapping() -> TrackerMapping:
    return TrackerMapping.load(MAPPING_FILE)


def fake_board(tracker: TrackerMapping, people: dict[str, str] | None = None) -> FakeBoard:
    """A board offering exactly the mapping's types, states and fields (plus one free field)."""
    types = {}
    for kind in KINDS:
        item = tracker.item(kind)
        fields = set(item.fields.values()) | tracker.person_input_fields(kind) | {FREE_FIELD}
        types[item.type] = BoardType(
            item.type, tuple(sorted(tracker.states_used(kind))), frozenset(fields)
        )
    first = {
        tracker.item("usecase").type: next(
            iter(tracker._data["items"]["usecase"]["columns"].values())  # noqa: SLF001
        ),
        tracker.item("run").type: tracker.run_item_state("opened"),
        tracker.item("clarification").type: tracker.clarification_open,
    }
    return FakeBoard(
        types=types,
        areas=frozenset({tracker.area}),
        identities={SERVICE: "ADLC Platform", **(people or {})},
        service_identity=SERVICE,
        state_field=tracker.field("usecase", "state"),
        initial_states=first,
    )


def inbox_for(h: Harness) -> InboxService:
    files = FileStore(
        Path(tempfile.mkdtemp(prefix="board_files_")),
        max_bytes=1_000_000,
        allowed_types=DEFAULT_ATTACHMENT_TYPES,
    )
    ledger = LedgerService(h.orch.runs, LedgerContentStore(files))
    return InboxService(h.orch.runs, ledger, DEADLETTER_ROLE, REPO_ROOT / "adlc-specs")


# ------------------------------------------------------------------ the full loop (US2-US9)


def board_user(role: str) -> str:
    """The board identity of the harness's person for ``role`` (tests.support.orchestration)."""
    return f"{role.replace('_', '.')}@board.test"


class Rig:
    """The platform (harness), a FakeBoard, the projector and inbound sync, wired together.

    Every harness person (``person(role)``) has a board identity ``board_user(role)``.
    """

    def __init__(
        self,
        h: Harness,
        roles: list[str] | None = None,
        extra: dict[str, tuple[str, frozenset[str]]] | None = None,
    ) -> None:
        """``extra``: more board users, board identity -> (account name, roles)."""
        from adlc.engagement.identities import BoardIdentities
        from adlc.engagement.inbound import InboundSync
        from adlc.engagement.projector import Projector
        from adlc.identity.accounts import Account
        from adlc.identity.catalogue import load_role_ids

        self.h = h
        self.mapping = mapping()
        all_roles = roles or sorted(
            load_role_ids(REPO_ROOT / "adlc-specs" / "shared" / "roles.yaml")
        )
        accounts = {
            f"{r}-person": Account(f"{r}-person", f"{r} person", frozenset({r}), "x", board_user(r))
            for r in all_roles
        }
        for identity, (name, held) in (extra or {}).items():
            accounts[name] = Account(name, f"{name} person", held, "x", identity)
        people = {board_user(r): f"{r} person" for r in all_roles}
        people.update({identity: name for identity, (name, _) in (extra or {}).items()})
        self.board = fake_board(self.mapping, people)
        self.identities = BoardIdentities(accounts, SERVICE)
        self.inbox = inbox_for(h)
        self.projector = Projector(h.app, self.inbox, self.board, self.mapping, EVIDENCE, h.clock)
        self.sync = InboundSync(
            h.app, h.service, self.board, self.mapping, self.identities, self.projector, h.clock
        )
        self.sync.poll()  # first start: an empty board, nothing to replay

    def cycle(self, rounds: int = 3) -> None:
        """Project, poll and let the platform move, until things settle."""
        for _ in range(rounds):
            self.projector.run_once()
            self.sync.poll()
            self.h.drain()
        self.projector.run_once()

    def as_role(self, role: str) -> FakeBoard:
        return self.board.as_user(board_user(role))

    def item(self, kind: str, object_id: str) -> int:
        from adlc.engagement import store

        with self.h.app.connect() as conn:
            link = store.get_link(conn, kind, object_id)
        assert link is not None, (kind, object_id)
        return link.work_item_id

    def comments(self, kind: str, object_id: str) -> list[str]:
        return [text for _, text in self.board.comments(self.item(kind, object_id))]

    def outcomes(self) -> list[tuple[str, str | None]]:
        rows = self.h.sql(
            "SELECT outcome, reason_code FROM inbound_outcome o JOIN inbound_change c "
            "USING (work_item_id, update_id) WHERE c.kind NOT IN ('own', 'baseline') "
            "ORDER BY o.at, o.work_item_id, o.update_id"
        )
        return [(str(r[0]), r[1]) for r in rows]


def needed_roles(h: Harness, run_id: str) -> list[str]:
    """Sign-off roles the run still needs (as ``Harness.pass_run`` computes them)."""
    run = h.run(run_id)
    with h.app.connect() as conn:
        ctx = h.orch.runs.context(conn, run)
    approved = {role for _, role in ctx.approvals}
    return sorted(ctx.required_plus_roles - approved) + sorted(ctx.rule_roles - approved)


def board_pass(rig: Rig, run_id: str, fields: dict[str, str] | None = None) -> None:
    """Pass a run from the board, as each still-needed approver, typing the values a pass
    emits in the Values field (the board twin of ``Harness.pass_run``)."""
    from adlc.engagement.model import ItemWrite
    from adlc.orchestration import routing

    h = rig.h
    h.drain()
    run = h.run(run_id)
    spec = h.orch.runs.entry(run.terminal_id, run.spec_version).spec
    given = dict(fields or {})
    missing = routing.emitted_values(spec, run.artifacts, {"usecase_id": run.usecase_id}, given)
    given.update({name: f"{name} (typed)" for name in missing.missing})
    values = "\n".join(f"{k}: {v}" for k, v in given.items())
    for _ in range(8):
        if h.run(run_id).state == "closed":
            break
        role = needed_roles(h, run_id)[0]
        write = {rig.mapping.decision_field: rig.mapping.value_for("pass")}
        if values:
            write[rig.mapping.inputs()["values"].field] = values
        rig.as_role(role).update(rig.item("run", run_id), ItemWrite(set=write))
        rig.cycle()
    assert h.run(run_id).state == "closed", h.run(run_id).state


def enable_board(api: Api, coe: str = DEADLETTER_ROLE) -> None:
    """Give the API an engagement layer over a FakeBoard (as the board process builds it), so
    the API answers as when ``ADLC_BOARD_ENABLED`` is true (016 API tests, 019 console tests)."""
    from pydantic import SecretStr

    from adlc.config.settings import BoardSettings
    from adlc.engagement.wiring import build

    services = api.app.state.services
    settings = BoardSettings(
        env="dev",
        db_path=services.settings.db_path,
        accounts_file=services.settings.accounts_file,
        deadletter_role=coe,
        board_enabled=True,
        board_url="http://board.test",
        board_organization="org",
        board_project="project",
        board_token=SecretStr("t" * 32),
        board_service_identity=SERVICE,
        board_evidence_url=EVIDENCE,
        board_mapping_file=MAPPING_FILE,
    )
    api.app.state.engagement = build(settings, services=services, board=fake_board(mapping()))
