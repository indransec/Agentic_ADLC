"""What a board decision or answer says, read before the platform is asked (FR-015, FR-028;
contracts/inbound-rules.md §3 and §5; research R-10).

Pure. ``read_inputs`` takes the run item's fields as of the decision's revision: each input from
its own field, or, when the field is empty, from a ``<label>: <value>`` line of the decision
comment (``value <name>: <v>`` for a value); the field wins over a differing line. It checks the
inputs against the run's decision form so a refusal can name the input and what is allowed; the
platform checks everything again. ``split_answers`` reads a clarification answer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from adlc.engagement.mapping import TrackerMapping

COMMENT_MAX = 4000  # the platform's limits on a decision (api/routes/runs.py)
REASON_MAX = 2000
SIGN_OFF_ACTIONS = ("pass", "rework", "exception", "terminate")
NAMED_INPUTS = ("root_cause", "reason", "target_terminal")
_NUMBERED = re.compile(r"^\s*(\d+)\s*[.)]\s*(.*)$")
_VALUE_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")


@dataclass(frozen=True)
class Refusal:
    code: str  # a reason code of inbound_outcome
    message: str


@dataclass(frozen=True)
class Inputs:
    comment: str | None = None
    root_cause: str | None = None
    reason: str | None = None
    target_terminal: str | None = None
    fields: Mapping[str, str] = field(default_factory=dict)
    overridden: tuple[str, ...] = ()  # inputs given in both places, where the field won


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _label_pattern(label: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in label.split())
    return re.compile(rf"^\s*{words}\s*:\s*(.*?)\s*$", re.IGNORECASE)


def _value_pattern(label: str) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in label.split())
    return re.compile(rf"^\s*{words}\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", re.IGNORECASE)


def _comment_lines(
    text: str | None, mapping: TrackerMapping
) -> tuple[str | None, dict[str, str], dict[str, str]] | Refusal:
    """Split the comment into its text, the named inputs and the values it carries."""
    if text is None:
        return None, {}, {}
    inputs = mapping.inputs()
    named = {name: _label_pattern(inputs[name].label) for name in NAMED_INPUTS}
    values_pattern = _value_pattern(inputs["values"].label)
    found: dict[str, str] = {}
    values: dict[str, str] = {}
    kept: list[str] = []
    for line in text.splitlines():
        value_match = values_pattern.match(line)
        if value_match is not None:
            name = value_match.group(1)
            if name in values:
                return Refusal("invalid_input", f"the value {name} is given twice in the comment")
            values[name] = value_match.group(2)
            continue
        for name, pattern in named.items():
            match = pattern.match(line)
            if match is not None:
                if name in found:
                    label = inputs[name].label
                    return Refusal("invalid_input", f"'{label}' is given twice in the comment")
                found[name] = match.group(1)
                break
        else:
            kept.append(line)
    return _clean("\n".join(kept)), found, values


def _values_field(text: str | None, label: str) -> dict[str, str] | Refusal:
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        match = _VALUE_LINE.match(line)
        if match is None:
            return Refusal("invalid_input", f"each line of the {label}s field is 'name: value'")
        values[match.group(1)] = match.group(2)
    return values


def read_inputs(
    action: str,
    fields_at_rev: Mapping[str, Any],
    mapping: TrackerMapping,
    form: Mapping[str, Any] | None,
) -> Inputs | Refusal:
    inputs = mapping.inputs()
    parsed = _comment_lines(_clean(fields_at_rev.get(mapping.comment_field)), mapping)
    if isinstance(parsed, Refusal):
        return parsed
    comment, from_lines, line_values = parsed
    field_values = _values_field(
        _clean(fields_at_rev.get(inputs["values"].field)), inputs["values"].label
    )
    if isinstance(field_values, Refusal):
        return field_values

    chosen: dict[str, str | None] = {}
    overridden: list[str] = []
    for name in NAMED_INPUTS:
        in_field = _clean(fields_at_rev.get(inputs[name].field))
        in_line = _clean(from_lines.get(name))
        chosen[name] = in_field or in_line
        if in_field and in_line and in_field != in_line:
            overridden.append(name)
    values = dict(line_values)
    for name, value in field_values.items():
        if name in values and values[name] != value:
            overridden.append(f"value {name}")
        values[name] = value

    if comment is not None and len(comment) > COMMENT_MAX:
        return Refusal("invalid_input", f"the comment is longer than {COMMENT_MAX} characters")
    reason = chosen["reason"]
    if reason is not None and len(reason) > REASON_MAX:
        return Refusal(
            "invalid_input", f"'{inputs['reason'].label}' is longer than {REASON_MAX} characters"
        )
    result = Inputs(
        comment=comment,
        root_cause=chosen["root_cause"],
        reason=reason,
        target_terminal=chosen["target_terminal"],
        fields=values,
        overridden=tuple(overridden),
    )
    if action not in SIGN_OFF_ACTIONS or form is None:
        return result
    return _check(action, result, mapping, form) or result


def _check(
    action: str, got: Inputs, mapping: TrackerMapping, form: Mapping[str, Any]
) -> Refusal | None:
    inputs = mapping.inputs()
    missing: list[str] = []
    # The platform's own rules (OrchestratorService._validate): a rework always needs a comment
    # and a root cause, a terminate a comment or a reason; the outcome's other requirements are
    # values, except the owner's comment, which is the comment.
    if action == "rework":
        if got.comment is None:
            missing.append("comment")
        if got.root_cause is None:
            missing.append(inputs["root_cause"].label)
    if action == "terminate" and got.comment is None and got.reason is None:
        missing.append(inputs["reason"].label)
    for need in form.get("requires", {}).get(action, []):
        if need in ("comment", "owner_comment", "root_cause") or (
            action == "terminate" and need == "reason"
        ):
            continue
        if need in NAMED_INPUTS:
            if getattr(got, need) is None:
                missing.append(inputs[need].label)
        elif need not in got.fields:
            missing.append(f"{inputs['values'].label} {need}")
    if action == "pass":
        missing += [
            f"{inputs['values'].label} {name}"
            for name in form.get("typed_fields", [])
            if name not in got.fields
        ]
    if action == "rework" and got.root_cause is not None:
        causes = [str(c) for c in form.get("root_causes", [])]
        if got.root_cause not in causes:
            return Refusal(
                "invalid_input",
                f"'{inputs['root_cause'].label}' {got.root_cause} is not allowed; "
                f"allowed: {', '.join(causes)}",
            )
        if got.root_cause in form.get("target_terminal_for", []) and got.target_terminal is None:
            missing.append(inputs["target_terminal"].label)
    if got.target_terminal is not None:
        terminals = [str(t) for t in form.get("target_terminals", [])]
        if got.target_terminal not in terminals:
            return Refusal(
                "invalid_input",
                f"'{inputs['target_terminal'].label}' {got.target_terminal} is not allowed; "
                f"allowed: {', '.join(terminals)}",
            )
    if missing:
        return Refusal("missing_input", f"{mapping.value_for(action)} needs: {', '.join(missing)}")
    return None


def split_answers(text: str | None, count: int) -> list[str] | Refusal:
    """One answer per question: the whole text for one question, else numbered lines 1..count."""
    body = (text or "").strip()
    if not body:
        return Refusal("invalid_input", "the answer is empty")
    if count == 1:
        return [body]
    answers: list[list[str]] = []
    for line in body.splitlines():
        match = _NUMBERED.match(line)
        if match is not None:
            if int(match.group(1)) != len(answers) + 1:
                return _count_refusal(count)
            answers.append([match.group(2).strip()])
        elif not answers:
            return _count_refusal(count)
        elif line.strip():
            answers[-1].append(line.strip())
    if len(answers) != count:
        return _count_refusal(count)
    return ["\n".join(part for part in parts if part) for parts in answers]


def _count_refusal(count: int) -> Refusal:
    return Refusal(
        "invalid_input",
        f"{count} questions need {count} answers, numbered 1. to {count}. on their own lines",
    )
