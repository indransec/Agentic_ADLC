"""Inbound sync: people's board changes become platform requests (US2-US6; FR-010..FR-018,
FR-024; contracts/inbound-rules.md; research R-04..R-07, R-09).

One ``poll``: ask the board for items changed at or after the watermark (its own ``asOf``), read
each item's updates not yet read, and handle them in order. Every update is claimed
(``inbound_change``) before anything happens and gets one outcome (``inbound_outcome``), so the
same update never becomes a second command. A request is applied through the same
``OrchestratorService`` call the inbox makes, as the board user's mapped account, with the update
as its ``source``. Every board change is a request: a refusal, an unmapped user or a person's change
to a platform-written field is reverted on the board with a comment giving the reason. The
watermark moves only when every item of the poll was handled.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine

from adlc.engagement import store
from adlc.engagement.classify import (
    ANSWER,
    DECIDE,
    IGNORED,
    OWN,
    REGISTER,
    REVERT,
    Action,
    classify,
)
from adlc.engagement.identities import BoardIdentities
from adlc.engagement.inputs import Inputs, Refusal, read_inputs, split_answers
from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.model import BoardItem, BoardUpdate, ItemWrite
from adlc.engagement.port import (
    BoardAdapter,
    BoardAuthFailed,
    BoardError,
    BoardUnreachable,
    RevisionConflict,
)
from adlc.engagement.projector import SYSTEM_ACTOR, Projector
from adlc.orchestration import store as run_store
from adlc.orchestration.engine import StaleRun, UnknownRun
from adlc.orchestration.interfaces import Clock
from adlc.orchestration.service import (
    Actor,
    AlreadyAnswered,
    InvalidDecision,
    NoActiveSpecs,
    NotAuthorised,
    OrchestratorService,
)
from adlc.orchestration.states import InvalidTransition
from adlc.orchestration.tracing import span

log = logging.getLogger(__name__)
PREFIX = "ADLC: "
_TAGS = re.compile(r"<[^>]+>")
_BLOCKS = re.compile(r"</(p|div|li)>|<br\s*/?>", re.IGNORECASE)


@dataclass(frozen=True)
class PollResult:
    outcome: str  # ok | board_unreachable | auth_failed | failed
    items: int = 0
    updates: int = 0


def _plain(value: Any) -> str:
    """HTML from the board's description field as plain text."""
    text = _BLOCKS.sub("\n", str(value or ""))
    return html.unescape(_TAGS.sub("", text)).strip()


def _usecase_of(object_id: str) -> str:
    return object_id.split("/", 1)[0]


class InboundSync:
    def __init__(
        self,
        engine: Engine,
        orchestration: OrchestratorService,
        board: BoardAdapter,
        mapping: TrackerMapping,
        identities: BoardIdentities,
        projector: Projector,
        clock: Clock,
        start_from: str | None = None,
    ) -> None:
        self.engine = engine
        self.orchestration = orchestration
        self.board = board
        self.mapping = mapping
        self.identities = identities
        self.projector = projector
        self.clock = clock
        self.start_from = start_from

    # ------------------------------------------------------------------ polling

    def poll(self) -> PollResult:
        with span("board", "poll"):
            try:
                return self._poll()
            except BoardUnreachable as error:
                return self._record("board_unreachable", str(error))
            except BoardAuthFailed as error:
                return self._record("auth_failed", str(error))
            except BoardError as error:
                return self._record("board_unreachable", f"{type(error).__name__}: {error}")

    def _record(
        self, outcome: str, error: str | None, items: int = 0, updates: int = 0
    ) -> PollResult:
        with self.engine.begin() as conn:
            store.record_poll(conn, outcome, error, self.clock.now())
        if error:
            log.warning("board poll %s: %s", outcome, error)
        return PollResult(outcome if outcome != "ok" or error is None else "failed", items, updates)

    def _poll(self) -> PollResult:
        with self.engine.connect() as conn:
            watermark = store.sync_state(conn).watermark
        if watermark is None and self.start_from is None:
            return self._baseline()
        page = self.board.changed_since(watermark or self.start_from)
        handled = 0
        for item_id in page.item_ids:
            try:
                handled += self._item(item_id)
            except BoardError:
                raise  # the board failed: the watermark stays, the next poll re-reads
            except Exception:
                log.exception("board item %s could not be handled; the watermark stays", item_id)
                return self._record("ok", f"item {item_id} failed", len(page.item_ids), handled)
        with self.engine.begin() as conn:
            store.set_watermark(conn, page.as_of)
        return self._record("ok", None, len(page.item_ids), handled)

    def _baseline(self) -> PollResult:
        """First start (FR-010a): mark the board's existing history as read; replay nothing."""
        page = self.board.changed_since(None)
        now = self.clock.now()
        for item_id in page.item_ids:
            for update in self.board.updates(item_id):
                with self.engine.begin() as conn:
                    claim = store.Claim(
                        item_id,
                        update.update_id,
                        update.rev,
                        update.changed_by,
                        None,
                        "baseline",
                        None,
                    )
                    if store.claim(conn, claim, now):
                        store.write_outcome(conn, item_id, update.update_id, "ignored", now)
                    store.set_inbound_update(conn, item_id, update.update_id, now)
        with self.engine.begin() as conn:
            store.set_watermark(conn, page.as_of)
        log.info("board baseline: %d items marked as read", len(page.item_ids))
        return self._record("ok", None, len(page.item_ids), 0)

    def _item(self, item_id: int) -> int:
        with self.engine.connect() as conn:
            after = store.max_update_id(conn, item_id)
        updates = self.board.updates(item_id, after)
        for update in updates:
            self._process(update)
        return len(updates)

    # ------------------------------------------------------------------ one update

    def _process(self, update: BoardUpdate, *, claimed: bool = False) -> None:
        item_id = update.item_id
        with span("board", "change"):
            with self.engine.connect() as conn:
                link = store.link_by_item(conn, item_id)
            at = self.board.get_at(item_id, update.rev)
            area_field = self.mapping.item("usecase").fields.get("area")
            area = None if area_field is None else at.fields.get(area_field)
            actions = classify(
                update,
                at.type,
                link,
                None if area is None else str(area),
                self.mapping,
                self.identities.service_identity,
            )
            kinds = [a.kind for a in actions]
            actor = self.identities.actor(update.changed_by)
            request = next((a for a in actions if a.kind in (REGISTER, DECIDE, ANSWER)), None)
            kind = (
                OWN
                if kinds == [OWN]
                else IGNORED
                if kinds == [IGNORED]
                else request.kind
                if request is not None
                else "revert_only"
            )
            now = self.clock.now()
            if not claimed:
                with self.engine.begin() as conn:
                    claim = store.Claim(
                        item_id,
                        update.update_id,
                        update.rev,
                        update.changed_by,
                        None if actor is None else actor.account_name,
                        kind,
                        None if link is None else link.object_id,
                    )
                    if not store.claim(conn, claim, now):
                        return  # already read: never a second command (FR-012)
            if kind in (OWN, IGNORED):
                self._outcome(update, "ignored")
                return
            reverted = False
            for action in actions:
                if action.kind == REVERT and link is not None:
                    self._revert_platform_fields(link, action)
                    reverted = True
            if request is None:
                self._outcome(
                    update,
                    "refused",
                    "platform_field",
                    "a platform-written field was changed",
                    reverted=reverted,
                )
                return
            if actor is None:
                reason = "the board user is not a mapped platform user"
                undone = self._refuse(update, at, request, link, reason)
                self._outcome(update, "refused", "not_mapped", reason, reverted=undone or reverted)
                return
            result = self._apply(request, update, at, link, actor)
            if isinstance(result, Refusal):
                undone = self._refuse(update, at, request, link, result.message)
                self._outcome(
                    update, "refused", result.code, result.message, reverted=undone or reverted
                )
            else:
                self._outcome(update, "accepted", command=result, reverted=reverted)

    def _outcome(
        self,
        update: BoardUpdate,
        outcome: str,
        code: str | None = None,
        reason: str | None = None,
        *,
        command: str | None = None,
        reverted: bool = False,
    ) -> None:
        now = self.clock.now()
        with self.engine.begin() as conn:
            store.write_outcome(
                conn,
                update.item_id,
                update.update_id,
                outcome,
                now,
                reason_code=code,
                reason=reason,
                command=command,
                reverted=reverted,
            )
            store.set_inbound_update(conn, update.item_id, update.update_id, now)
        log.info(
            "board change item=%s update=%s outcome=%s code=%s command=%s",
            update.item_id,
            update.update_id,
            outcome,
            code,
            command,
        )

    # ------------------------------------------------------------------ requests

    def _apply(
        self,
        request: Action,
        update: BoardUpdate,
        at: BoardItem,
        link: store.Link | None,
        actor: Actor,
    ) -> str | Refusal:
        source = {"board_item": update.item_id, "update": update.update_id}
        with span("board", "command"):
            try:
                if request.kind == REGISTER:
                    return self._register(update, at, actor, source)
                assert link is not None  # noqa: S101 - classify only asks for linked items here
                if request.kind == ANSWER:
                    return self._answer(link.object_id, request.value, actor, source, update)
                return self._decide(link.object_id, request.value, at, actor, source, update)
            except NotAuthorised as error:
                return Refusal("not_authorised", str(error))
            except InvalidDecision as error:
                return Refusal("invalid_input", str(error))
            except AlreadyAnswered:
                return Refusal("already_answered", "this clarification was already answered")
            except (InvalidTransition, StaleRun, UnknownRun) as error:
                return Refusal("stale", f"the run has moved on: {error}")

    def _register(
        self, update: BoardUpdate, at: BoardItem, actor: Actor, source: Mapping[str, int]
    ) -> str | Refusal:
        fields = self.mapping.item("usecase").fields
        name = str(at.fields.get(fields["title"]) or "").strip()
        intake = _plain(at.fields.get(fields["description"]))
        if not name or not intake:
            return Refusal(
                "invalid_usecase", "a use case needs a title and a description (its intake text)"
            )
        if len(name) > 200:
            return Refusal("invalid_usecase", "the title is longer than 200 characters")
        try:
            usecase = self.orchestration.submit_usecase(actor, name, intake, source=source)
        except NoActiveSpecs as error:
            return Refusal("invalid_usecase", str(error))
        with self.engine.begin() as conn:
            store.put_link(
                conn, "usecase", usecase, update.item_id, at.type, self.clock.now(), rev=at.rev
            )
        self.projector.mark_dirty(usecase)
        self._comment(
            update.item_id, f"registered as use case {usecase} by {self._display(update)}."
        )
        return "submit_usecase"

    def _answer(
        self,
        clarification_id: str,
        text: str | None,
        actor: Actor,
        source: Mapping[str, int],
        update: BoardUpdate,
    ) -> str | Refusal:
        with self.engine.connect() as conn:
            round_ = run_store.load_clarification(conn, clarification_id)
        if round_ is None:
            return Refusal("stale", f"no clarification {clarification_id}")
        questions = round_["questions"]
        questions = json.loads(questions) if isinstance(questions, str) else questions
        answers = split_answers(text, len(questions or []) or 1)
        if isinstance(answers, Refusal):
            return answers
        self.orchestration.answer_clarification(actor, clarification_id, answers, source=source)
        self._comment(update.item_id, f"answers by {self._display(update)} accepted.")
        return "answer_clarification"

    def _decide(
        self,
        run_id: str,
        value: str | None,
        at: BoardItem,
        actor: Actor,
        source: Mapping[str, int],
        update: BoardUpdate,
    ) -> str | Refusal:
        action = self.mapping.action_for(value)
        if action is None:
            allowed = ", ".join(self.mapping.allowed_values())
            return Refusal("unknown_value", f"{value!r} is not a decision; use one of: {allowed}")
        run = self.orchestration.get_run(run_id)
        if run is None:
            return Refusal("stale", f"no run {run_id}")
        usecase = self.orchestration.get_usecase(run.usecase_id)
        if usecase is not None and usecase.status != "active":
            return Refusal("closed", f"use case {run.usecase_id} is {usecase.status}")
        form = None
        if str(run.state) == "awaiting_sign_off":
            form = self.projector.inbox.detail(run_id, SYSTEM_ACTOR)["form"]
        inputs = read_inputs(action, at.fields, self.mapping, form)
        if isinstance(inputs, Refusal):
            return inputs
        self._call(action, run_id, actor, inputs, source)
        note = ""
        if inputs.overridden:
            note = f" ({', '.join(inputs.overridden)}: the field was used, not the comment line)"
        self._accept(
            update.item_id,
            f"{self.mapping.value_for(action)} by {self._display(update)} accepted{note}.",
        )
        return (
            f"decide:{action}" if action in ("pass", "rework", "exception", "terminate") else action
        )

    def _call(
        self, action: str, run_id: str, actor: Actor, inputs: Inputs, source: Mapping[str, int]
    ) -> None:
        def attempt(version: int) -> Any:
            if action in ("approve_waiver", "reject_waiver"):
                run = self.orchestration.get_run(run_id)
                if run is None or run.pending_waiver_id is None:
                    raise InvalidTransition(f"{run_id} has no pending waiver")
                return self.orchestration.decide_waiver(
                    actor,
                    run.pending_waiver_id,
                    action == "approve_waiver",
                    inputs.comment,
                    source=source,
                )
            if action == "complete_escalation":
                return self.orchestration.complete_escalation(
                    actor, run_id, {}, expected_version=version, source=source
                )
            return self.orchestration.decide(
                actor,
                run_id,
                action,
                comment=inputs.comment,
                root_cause=inputs.root_cause,
                reason=inputs.reason,
                fields=dict(inputs.fields),
                target_terminal=inputs.target_terminal,
                expected_version=version,
                source=source,
            )

        _retry_once(lambda: self._version(run_id), attempt)

    def _version(self, run_id: str) -> int:
        run = self.orchestration.get_run(run_id)
        if run is None:
            raise UnknownRun(run_id)
        return run.version

    # ------------------------------------------------------------------ replies

    def _display(self, update: BoardUpdate) -> str:
        return self.identities.display_name(update.changed_by) or update.changed_by

    def _comment(self, item_id: int, text: str) -> None:
        try:
            self.board.comment(item_id, PREFIX + text)
        except BoardError as error:
            log.warning("board comment on %s failed: %s", item_id, type(error).__name__)

    def _accept(self, item_id: int, text: str) -> None:
        """Comment, and clear the run item's decision, comment and inputs for the next decision."""
        self._comment(item_id, text)
        fields = tuple(sorted(self.mapping.person_input_fields("run")))
        try:
            current = self.board.get(item_id)
            if any(current.fields.get(f) not in (None, "") for f in fields):
                self.board.update(item_id, ItemWrite(clear=fields, expected_rev=current.rev))
        except RevisionConflict:
            pass  # someone changed it since: the next poll reads that change
        except BoardError as error:
            log.warning("clearing the decision on %s failed: %s", item_id, type(error).__name__)

    def _refuse(
        self,
        update: BoardUpdate,
        at: BoardItem,
        request: Action,
        link: store.Link | None,
        reason: str,
    ) -> bool:
        """Comment the reason and clear the request field (the decision, or the answer) if it still
        holds this update's value; the comment and inputs stay so the person can complete them and
        decide again. Registration is not reverted (an edit is a new request)."""
        self._comment(update.item_id, f"refused — {reason}")
        if request.kind == REGISTER or link is None:
            return False
        field = (
            self.mapping.decision_field
            if link.object_kind == "run"
            else self.mapping.field("clarification", "answer")
        )
        change = update.fields.get(field)
        if change is None:
            return False
        try:
            current = self.board.get(update.item_id)
            if current.fields.get(field) != change.new:
                return False  # changed again since: the next update is read on its own
            self.board.update(update.item_id, ItemWrite(clear=(field,), expected_rev=current.rev))
            return True
        except RevisionConflict:
            return False
        except BoardError as error:
            log.warning(
                "clearing a refused request on %s failed: %s", update.item_id, type(error).__name__
            )
            return False

    def _revert_platform_fields(self, link: store.Link, action: Action) -> None:
        usecase = _usecase_of(link.object_id)
        for item in self.projector.items_for(usecase):
            if (item.kind, item.object_id) == (link.object_kind, link.object_id):
                changed = self.projector.write(item, force=True)
                if changed:
                    names = ", ".join(sorted(action.fields))
                    self._comment(
                        link.work_item_id, f"{names} is set by the platform; changed back."
                    )
                return

    # ------------------------------------------------------------------ recovery (R-07)

    def recover(self) -> int:
        """Finish updates claimed before a stop: accepted if the platform recorded the command,
        else handled again. Returns how many were resolved."""
        with self.engine.connect() as conn:
            pending = store.unresolved_claims(conn)
        resolved = 0
        for claim in pending:
            with self.engine.connect() as conn:
                done = store.activity_with_source(conn, claim.work_item_id, claim.update_id)
            if done:
                with self.engine.begin() as conn:
                    store.write_outcome(
                        conn,
                        claim.work_item_id,
                        claim.update_id,
                        "accepted",
                        self.clock.now(),
                        command="recovered",
                    )
                resolved += 1
                continue
            updates = self.board.updates(claim.work_item_id, claim.update_id - 1)
            update = next((u for u in updates if u.update_id == claim.update_id), None)
            if update is not None:
                self._process(update, claimed=True)
                resolved += 1
        return resolved


def _retry_once(version: Callable[[], int], attempt: Callable[[int], Any]) -> Any:
    """Apply with the run's current version; once more if the orchestrator moved it meanwhile."""
    try:
        return attempt(version())
    except StaleRun:
        return attempt(version())
