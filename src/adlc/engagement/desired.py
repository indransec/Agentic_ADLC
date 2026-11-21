"""The desired board state of one use case (FR-005, FR-006; research R-03, R-13).

``desired`` is pure: from a snapshot of the platform's records it returns one item per use case,
run and clarification round, with the platform-written field values (compared and hashed: a
person's change to them is reverted) and the values set only when an item is created (title,
description and area of the Epic, which a person may edit afterwards). Every board name comes from
the mapping. ``snapshot`` reads the platform's tables and the run's decision form through the
inbox's read side, so the board offers exactly what the inbox offers.
"""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from adlc.engagement.mapping import TrackerMapping

if TYPE_CHECKING:
    from sqlalchemy import Connection

    from adlc.inbox.service import InboxService

CLOSED = "closed"
TERMINATED = "terminate"


@dataclass(frozen=True)
class ClarificationSnapshot:
    clarification_id: str
    addressed_role: str
    questions: tuple[str, ...]
    answered_by: str | None


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    terminal_id: str
    run_number: int
    state: str
    final_status: str | None
    form: Mapping[str, Any] | None
    recommendation: Mapping[str, Any] | None
    approvals: tuple[tuple[str, str], ...]  # (person, role) of passes that still count
    waiting_roles: tuple[str, ...]  # sign-off roles still needed
    waiver: Mapping[str, Any] | None  # the pending waiver: id, status, approver roles
    clarifications: tuple[ClarificationSnapshot, ...] = ()


@dataclass(frozen=True)
class UseCaseSnapshot:
    usecase_id: str
    name: str
    intake_text: str
    status: str  # active | terminated | closed
    runs: tuple[RunSnapshot, ...] | Sequence[RunSnapshot]


@dataclass(frozen=True)
class DesiredItem:
    kind: str  # usecase | run | clarification
    object_id: str
    item_type: str
    parent: tuple[str, str] | None  # (kind, object id) of the parent item
    fields: Mapping[str, Any]  # platform-written values (hashed, kept in step)
    create_fields: Mapping[str, Any] = field(default_factory=dict)  # set once, at creation

    @property
    def hash(self) -> str:
        text = json.dumps(
            {"type": self.item_type, **dict(self.fields)}, sort_keys=True, default=str
        )
        return hashlib.sha256(text.encode()).hexdigest()


def desired(
    usecase: UseCaseSnapshot, mapping: TrackerMapping, evidence_url: str
) -> list[DesiredItem]:
    items = [_usecase_item(usecase, mapping)]
    terminated = usecase.status == "terminated"
    for run in usecase.runs:
        items.append(_run_item(usecase, run, mapping, evidence_url, terminated))
        items += [_clarification_item(run, round_, mapping) for round_ in run.clarifications]
    return items


# ------------------------------------------------------------------------------ items


def _current(usecase: UseCaseSnapshot) -> RunSnapshot | None:
    """The run the Epic follows: the latest open run, else the latest run."""
    runs = list(usecase.runs)
    open_runs = [r for r in runs if r.state != CLOSED]
    if open_runs:
        return open_runs[-1]
    return runs[-1] if runs else None


def _usecase_item(usecase: UseCaseSnapshot, mapping: TrackerMapping) -> DesiredItem:
    current = _current(usecase)
    if usecase.status == "terminated":
        state = mapping.terminated_state("usecase")
    elif usecase.status == CLOSED:
        state = mapping.closed_column
    elif current is not None:
        state = mapping.column(current.terminal_id) or mapping.closed_column
    else:
        state = _first_column(mapping)
    sub_stage = mapping.sub_stage(current.state if current is not None else "opened")
    if usecase.status != "active":
        sub_stage = mapping.sub_stage(CLOSED)
    f = mapping.item("usecase").fields
    return DesiredItem(
        kind="usecase",
        object_id=usecase.usecase_id,
        item_type=mapping.item("usecase").type,
        parent=None,
        fields={f["state"]: state, f["sub_stage"]: sub_stage, f["usecase_id"]: usecase.usecase_id},
        create_fields={
            f["title"]: usecase.name,
            f["description"]: _paragraphs(usecase.intake_text),
            **({f["area"]: mapping.area} if "area" in f else {}),
        },
    )


def _first_column(mapping: TrackerMapping) -> str:
    columns: Mapping[str, str] = mapping._data["items"]["usecase"]["columns"]  # noqa: SLF001
    return str(next(iter(columns.values())))


def _run_item(
    usecase: UseCaseSnapshot,
    run: RunSnapshot,
    mapping: TrackerMapping,
    evidence_url: str,
    terminated: bool,
) -> DesiredItem:
    f = mapping.item("run").fields
    if run.final_status == TERMINATED or (terminated and run.state != CLOSED):
        state = mapping.terminated_state("run")
    else:
        state = mapping.run_item_state(run.state)
    return DesiredItem(
        kind="run",
        object_id=run.run_id,
        item_type=mapping.item("run").type,
        parent=("usecase", usecase.usecase_id),
        fields={
            f["title"]: f"{run.terminal_id} run {run.run_number}",
            f["description"]: _run_description(run, mapping),
            f["state"]: state,
            f["run_id"]: run.run_id,
            f["evidence"]: evidence_url + quote(run.run_id, safe=""),
        },
    )


def _clarification_item(
    run: RunSnapshot, round_: ClarificationSnapshot, mapping: TrackerMapping
) -> DesiredItem:
    f = mapping.item("clarification").fields
    number = round_.clarification_id.rsplit("-", 1)[-1]
    questions = "".join(
        f"<p>{i}. {html.escape(q)}</p>" for i, q in enumerate(round_.questions, start=1)
    )
    answered = round_.answered_by is not None
    status = (
        f"<p>Answered by {html.escape(str(round_.answered_by))}.</p>"
        if answered
        else "<p>Answer in the answer field, one numbered line per question.</p>"
    )
    return DesiredItem(
        kind="clarification",
        object_id=round_.clarification_id,
        item_type=mapping.item("clarification").type,
        parent=("run", run.run_id),
        fields={
            f["title"]: f"{run.terminal_id} run {run.run_number}: clarification {number}",
            f["description"]: (
                f"<p>For the role {html.escape(round_.addressed_role)}.</p>{questions}{status}"
            ),
            f["state"]: mapping.clarification_answered if answered else mapping.clarification_open,
            f["clarification_id"]: round_.clarification_id,
        },
    )


# ------------------------------------------------------------------------------ text


def _paragraphs(text: str) -> str:
    return "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip())


def _items(values: Sequence[str]) -> str:
    return ", ".join(html.escape(str(v)) for v in values)


def _needs(outcome: str, form: Mapping[str, Any], inputs: Mapping[str, Any]) -> list[str]:
    """What a decision needs, in the board's words (the platform's rules, inputs.py)."""
    needs: list[str] = []
    if outcome == "rework":
        needs += ["comment", inputs["root_cause"].label]
    if outcome == "terminate":
        needs.append(f"comment or {inputs['reason'].label}")
    for name in form.get("requires", {}).get(outcome, []):
        if name in ("comment", "owner_comment", "root_cause") or (
            outcome == "terminate" and name == "reason"
        ):
            continue
        needs.append(inputs[name].label if name in inputs else f"{inputs['values'].label} {name}")
    return needs


def _run_description(run: RunSnapshot, mapping: TrackerMapping) -> str:
    parts = [f"<p>State: {html.escape(mapping.sub_stage(run.state))}.</p>"]
    if run.final_status is not None:
        parts.append(f"<p>Closed as {html.escape(run.final_status)}.</p>")
    form = run.form or {}
    outcomes = [str(o) for o in form.get("outcomes", [])]
    if outcomes:
        inputs = mapping.inputs()
        choices = []
        for outcome in outcomes:
            needs = _needs(outcome, form, inputs)
            label = html.escape(mapping.value_for(outcome))
            choices.append(
                f"<li>{label}" + (f" (needs: {_items(needs)})" if needs else "") + "</li>"
            )
        parts.append(
            "<p>Decide by setting the decision field to one of:</p><ul>"
            + "".join(choices)
            + "</ul>"
        )
        if form.get("root_causes"):
            parts.append(f"<p>Root causes: {_items(form['root_causes'])}.</p>")
        if form.get("target_terminal_for"):
            terminals = _items(form.get("target_terminals", []))
            parts.append(
                f"<p>Root causes that need a rework target ({terminals}):"
                f" {_items(form['target_terminal_for'])}.</p>"
            )
        if form.get("typed_fields"):
            parts.append(f"<p>Values a pass must give: {_items(form['typed_fields'])}.</p>")
    if run.recommendation:
        status = html.escape(str(run.recommendation.get("status", "")))
        summary = html.escape(str(run.recommendation.get("summary", "") or ""))
        parts.append(f"<p>Reviewer recommends {status}. {summary}</p>")
    if run.approvals:
        approved = ", ".join(f"{html.escape(p)} ({html.escape(r)})" for p, r in run.approvals)
        parts.append(f"<p>Approved by {approved}.</p>")
    if run.state == "awaiting_sign_off" and run.waiting_roles:
        parts.append(f"<p>Waiting for: {_items(run.waiting_roles)}.</p>")
    if run.waiver:
        roles = _items(run.waiver.get("approver_roles", []))
        parts.append(
            f"<p>Waiver {html.escape(str(run.waiver.get('waiver_id')))} is pending: a person with "
            f"one of {roles} who did not propose it sets "
            f"{html.escape(mapping.value_for('approve_waiver'))} or "
            f"{html.escape(mapping.value_for('reject_waiver'))}.</p>"
        )
    if run.state == "escalated":
        parts.append(
            f"<p>Escalated: the accountable role sets "
            f"{html.escape(mapping.value_for('complete_escalation'))} once it is resolved.</p>"
        )
    return "".join(parts)


# ------------------------------------------------------------------------------ snapshot


def snapshot(
    conn: Connection, inbox: InboxService, usecase_id: str, system_actor: Any
) -> UseCaseSnapshot | None:
    """Read one use case and its runs as the projector needs them (no board call)."""
    from adlc.orchestration import store as run_store  # noqa: PLC0415 - keep desired() importable

    usecase = run_store.load_usecase(conn, usecase_id)
    if usecase is None:
        return None
    runs = []
    for run in run_store.runs_of_usecase(conn, usecase_id):
        rounds = tuple(
            ClarificationSnapshot(
                str(c["clarification_id"]),
                str(c["addressed_role"]),
                tuple(str(q) for q in (_json(c["questions"]) or [])),
                None if c["answered_by"] is None else str(c["answered_by"]),
            )
            for c in run_store.clarifications(conn, run.run_id)
        )
        form = recommendation = waiver = None
        approvals: tuple[tuple[str, str], ...] = ()
        waiting: tuple[str, ...] = ()
        if run.state != CLOSED:
            detail = inbox.detail(run.run_id, system_actor)
            form = detail["form"] if run.state == "awaiting_sign_off" else None
            recommendation = detail["recommendation"]
            approvals = tuple((str(a["person"]), str(a["role"])) for a in detail["approvals"])
            ctx = inbox.runs.context(conn, run)
            approved = {role for _, role in approvals}
            waiting = tuple(sorted((set(ctx.rule_roles) | set(ctx.required_plus_roles)) - approved))
            if detail["waiver"]:
                waiver = {
                    "waiver_id": detail["waiver"]["waiver_id"],
                    "status": detail["waiver"]["status"],
                    "approver_roles": sorted(_waiver_approvers(inbox, run)),
                }
        runs.append(
            RunSnapshot(
                run_id=run.run_id,
                terminal_id=run.terminal_id,
                run_number=run.run_number,
                state=str(run.state),
                final_status=run.final_status,
                form=form,
                recommendation=recommendation,
                approvals=approvals,
                waiting_roles=waiting,
                waiver=waiver,
                clarifications=rounds,
            )
        )
    return UseCaseSnapshot(
        usecase.usecase_id, usecase.name, usecase.intake_text, str(usecase.status), tuple(runs)
    )


def _waiver_approvers(inbox: InboxService, run: Any) -> set[str]:
    from adlc.inbox import rules  # noqa: PLC0415

    spec = inbox.runs.entry(run.terminal_id, run.spec_version).spec
    return set(rules.waiver_approvers(spec))


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
