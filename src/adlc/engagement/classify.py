"""How a board update is read (contracts/inbound-rules.md §1-§2; research R-05).

``classify`` is pure: given one update, the item's type, its link to a platform object (if any),
the item's area at that revision and the mapping, it returns what the update asks for. Guards that
need the platform (an unmapped user, a closed use case) are applied by inbound sync afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass

from adlc.engagement.mapping import TrackerMapping
from adlc.engagement.model import BoardUpdate
from adlc.engagement.store import Link

OWN, REGISTER, DECIDE, ANSWER, REVERT, IGNORED = (
    "own",
    "register_usecase",
    "decide",
    "answer",
    "revert",
    "ignored",
)
DECIDE_CHANGE = "decide_change"  # 020: a decision on a change request item


@dataclass(frozen=True)
class Action:
    kind: str
    value: str | None = None  # the decision value or the answer text
    fields: tuple[str, ...] = ()  # for a revert: the platform-written fields a person changed


def _new_value(update: BoardUpdate, field: str) -> str | None:
    change = update.fields.get(field)
    if change is None or change.new in (None, ""):
        return None
    return str(change.new)


def classify(
    update: BoardUpdate,
    item_type: str,
    link: Link | None,
    area: str | None,
    mapping: TrackerMapping,
    service_identity: str,
) -> list[Action]:
    if update.changed_by.lower() == service_identity.lower():
        return [Action(OWN)]
    if not update.is_revision:
        return [Action(IGNORED)]  # the other side of a link: nothing to read
    kind = link.object_kind if link is not None else mapping.kind_of_type(item_type)
    if kind is None:
        return [Action(IGNORED)]
    if link is None:
        return [_registration(update, kind, area, mapping)]
    actions: list[Action] = []
    written = tuple(sorted(set(update.fields) & mapping.platform_written(kind)))
    if written:
        actions.append(Action(REVERT, fields=written))
    if kind == "run":
        value = _new_value(update, mapping.decision_field)
        if value is not None:
            actions.append(Action(DECIDE, value=value))
    elif kind == "clarification":
        value = _new_value(update, mapping.field("clarification", "answer"))
        if value is not None:
            actions.append(Action(ANSWER, value=value))
    elif kind == "change":
        value = _new_value(update, mapping.decision_field)
        if value is not None:
            actions.append(Action(DECIDE_CHANGE, value=value))
    return actions or [Action(IGNORED)]


def _registration(
    update: BoardUpdate, kind: str, area: str | None, mapping: TrackerMapping
) -> Action:
    """An unlinked Epic in the mapped area, created or with a new title or description."""
    if kind != "usecase" or area != mapping.area:
        return Action(IGNORED)
    fields = mapping.item("usecase").fields
    touched = {fields["title"], fields["description"]} & set(update.fields)
    if update.update_id == 1 or touched:
        return Action(REGISTER)
    return Action(IGNORED)
