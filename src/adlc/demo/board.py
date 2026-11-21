"""The demo's people on the board (feature 020, research R-05, R-09).

With the board sync on, the demo driver's human steps are board changes made as the named demo
people through the board port (``BoardAdapter``: the ADO adapter with that person's token), never
platform calls. Every board name and value comes from the tracker mapping. After each write the
driver waits until the board sync has read it (an inbound outcome for that item) and fails the
step, with the platform's reason, when it was refused.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, text

from adlc.engagement import store
from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.model import ItemWrite
from adlc.engagement.port import BoardAdapter
from adlc.orchestration.service import Actor


class BoardStepFailed(Exception):
    """A board write was refused or never read; the message says which and why."""


@dataclass(frozen=True)
class Write:
    """One person's change to one board item."""

    actor: Actor
    kind: str  # the item kind: usecase, run, clarification, change
    object_id: str
    fields: Mapping[str, str]
    refusal_expected: bool = False  # D-12: a change the platform sets back


@dataclass
class BoardActor:
    engine: Engine
    mapping: TrackerMapping
    adapter_for: Callable[[Actor], BoardAdapter]  # a person's own board session
    user_of: Callable[[Actor], str]  # the person's board user (``board_identity``)
    service_board: BoardAdapter  # the platform's service account (D-13's drift only)
    wait: Callable[[], None]  # let the platform and the sync move (and pause in real time)
    rounds: int = 200
    log: list[dict[str, Any]] = field(default_factory=list)  # every write, for the report

    # ------------------------------------------------------------------ items

    def find(self, kind: str, object_id: str) -> int | None:
        with self.engine.connect() as conn:
            link = store.get_link(conn, kind, object_id)
        return None if link is None else link.work_item_id

    def item(self, kind: str, object_id: str) -> int:
        """The board item showing ``object_id``, waiting for the sync to project it."""
        for _ in range(self.rounds):
            found = self.find(kind, object_id)
            if found is not None:
                return found
            self.wait()
        raise BoardStepFailed(f"the {kind} item for {object_id} did not appear on the board")

    def url(self, kind: str, object_id: str) -> str:
        return self.service_board.item_url(self.item(kind, object_id))

    # ------------------------------------------------------------------ writing

    def _outcomes(self, item_id: int) -> list[tuple[str, str | None, str | None]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT o.outcome, o.reason_code, o.reason FROM inbound_outcome o "
                    "JOIN inbound_change c USING (work_item_id, update_id) "
                    "WHERE o.work_item_id = :i AND c.kind NOT IN ('own', 'baseline') "
                    "ORDER BY o.update_id"
                ),
                {"i": item_id},
            ).all()
        return [(str(r[0]), r[1], r[2]) for r in rows]

    def apply(self, write: Write) -> int:
        """Make the change as the person and wait until the sync has read it."""
        item_id = self.item(write.kind, write.object_id)
        before = len(self._outcomes(item_id))
        board = self.adapter_for(write.actor)
        board.update(item_id, ItemWrite(set=dict(write.fields)))
        self.log.append(
            {
                "person": self.user_of(write.actor),
                "item": item_id,
                "kind": write.kind,
                "object_id": write.object_id,
                "fields": sorted(write.fields),
            }
        )
        for _ in range(self.rounds):
            outcomes = self._outcomes(item_id)
            if len(outcomes) > before:
                outcome, code, reason = outcomes[-1]
                refused = outcome == "refused"
                if refused != write.refusal_expected:
                    said = f"refused ({code}: {reason})" if refused else outcome
                    raise BoardStepFailed(
                        f"{self.user_of(write.actor)}'s change to {write.kind} {write.object_id}"
                        f" was {said}"
                    )
                return item_id
            self.wait()
        raise BoardStepFailed(
            f"the board sync did not read {self.user_of(write.actor)}'s change to {write.kind} "
            f"{write.object_id} (is the board process running?)"
        )

    def create_usecase(self, actor: Actor, name: str, intake: str) -> int:
        """An Epic in the mapping's area, as the person (the sync registers it)."""
        item = self.mapping.item("usecase")
        fields = {
            item.fields["title"]: name,
            item.fields["description"]: "".join(
                f"<p>{html.escape(line)}</p>" for line in intake.splitlines() if line.strip()
            ),
        }
        if "area" in item.fields:
            fields[item.fields["area"]] = self.mapping.area
        created = self.adapter_for(actor).create(item.type, fields)
        self.log.append({"person": self.user_of(actor), "item": created.id, "kind": "usecase"})
        return created.id

    def drift(self, kind: str, object_id: str, field_key: str, value: str) -> tuple[int, str]:
        """D-13: change a platform-written field as the service account, which the sync reads
        as its own change and leaves alone, so the board is out of step (a demo device)."""
        item_id = self.item(kind, object_id)
        name = self.mapping.field(kind, field_key)
        self.service_board.update(item_id, ItemWrite(set={name: value}))
        return item_id, name

    def value(self, kind: str, object_id: str, field_key: str) -> Any:
        item_id = self.item(kind, object_id)
        return self.service_board.get(item_id).fields.get(self.mapping.field(kind, field_key))

    # ------------------------------------------------------------------ what people type

    def decision(
        self,
        action: str,
        *,
        comment: str | None = None,
        root_cause: str | None = None,
        reason: str | None = None,
        values: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
        """The decision field and its inputs, in the mapping's fields."""
        inputs = self.mapping.inputs()
        fields = {self.mapping.decision_field: self.mapping.value_for(action)}
        if comment:
            fields[self.mapping.comment_field] = comment
        if root_cause:
            fields[inputs["root_cause"].field] = root_cause
        if reason:
            fields[inputs["reason"].field] = reason
        if values:
            fields[inputs["values"].field] = "\n".join(f"{k}: {v}" for k, v in values.items())
        return fields

    def answer(self, count: int, text_: str) -> dict[str, str]:
        lines = "\n".join(f"{n}. {text_}" for n in range(1, max(1, count) + 1))
        return {self.mapping.field("clarification", "answer"): lines}

    def instruction(self, write: Write) -> str:
        """The presenter's line for one write: who, where, and every value to set."""
        labels = {self.mapping.decision_field: "decision", self.mapping.comment_field: "comment"}
        labels |= {spec.field: spec.label for spec in self.mapping.inputs().values()}
        labels[self.mapping.field("clarification", "answer")] = "answer"
        values = "; ".join(
            f"{labels.get(name, name)} = {value!r}" for name, value in write.fields.items()
        )
        return (
            f"As {self.user_of(write.actor)}, open {self.url(write.kind, write.object_id)} "
            f"and set {values}, then save."
        )
