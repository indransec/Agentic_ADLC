"""Decision inputs from fields and comment lines (T027; FR-015, FR-028; inbound-rules §3)."""

from pathlib import Path
from typing import Any

import pytest

from adlc.engagement.inputs import Inputs, Refusal, read_inputs
from adlc.engagement.mapping import TrackerMapping

ROOT = Path(__file__).resolve().parents[3]
MAPPING = TrackerMapping.load(ROOT / "adlc-specs" / "tracker_mapping.yaml")
INPUTS = MAPPING.inputs()
ROOT_CAUSE, REASON = INPUTS["root_cause"], INPUTS["reason"]
TARGET, VALUES = INPUTS["target_terminal"], INPUTS["values"]
FORM: dict[str, Any] = {
    "outcomes": ["pass", "rework", "exception", "terminate"],
    "requires": {
        "rework": ["owner_comment"],
        "terminate": ["reason"],
        "exception": ["waiver_owner", "expiry"],
    },
    "root_causes": ["requirement", "qualification"],
    "target_terminal_for": ["qualification"],
    "target_terminals": ["T0", "T1"],
    "typed_fields": ["risk_tier"],
}


def _read(action: str, comment: str | None = None, **fields: str) -> Inputs | Refusal:
    values = {INPUTS[name].field: value for name, value in fields.items()}
    if comment is not None:
        values[MAPPING.comment_field] = comment
    return read_inputs(action, values, MAPPING, FORM)


def _ok(result: Inputs | Refusal) -> Inputs:
    assert isinstance(result, Inputs), result
    return result


def _refused(result: Inputs | Refusal, code: str) -> str:
    assert isinstance(result, Refusal), result
    assert result.code == code, result
    return result.message


def test_inputs_from_fields() -> None:
    got = _ok(_read("rework", "KPI missing", root_cause="qualification", target_terminal="T0"))
    assert (got.comment, got.root_cause, got.target_terminal) == (
        "KPI missing",
        "qualification",
        "T0",
    )


def test_inputs_from_comment_lines() -> None:
    comment = (
        f"KPI missing\n{ROOT_CAUSE.label}: requirement\n  {REASON.label.upper()} :  late data  "
    )
    got = _ok(_read("rework", comment))
    assert got.root_cause == "requirement"
    assert got.reason == "late data"
    assert got.comment == "KPI missing"
    assert got.overridden == ()


def test_values_from_the_field_and_from_lines() -> None:
    assert _ok(_read("pass", values="risk_tier: high")).fields == {"risk_tier": "high"}
    got = _ok(_read("pass", f"ok\n{VALUES.label} risk_tier: low"))
    assert got.fields == {"risk_tier": "low"} and got.comment == "ok"


def test_the_field_wins_over_a_differing_line() -> None:
    got = _ok(_read("rework", f"c\n{ROOT_CAUSE.label}: qualification", root_cause="requirement"))
    assert got.root_cause == "requirement"
    assert got.overridden == ("root_cause",)


def test_unknown_labels_stay_comment_text() -> None:
    got = _ok(_read("rework", "c\nroot-cause: x\nnote: keep", root_cause="requirement"))
    assert got.comment == "c\nroot-cause: x\nnote: keep"


def test_a_repeated_label_is_refused() -> None:
    message = _refused(
        _read("rework", f"c\n{ROOT_CAUSE.label}: requirement\n{ROOT_CAUSE.label}: qualification"),
        "invalid_input",
    )
    assert ROOT_CAUSE.label in message


@pytest.mark.parametrize(
    ("action", "comment", "fields", "names"),
    [
        ("rework", None, {"root_cause": "requirement"}, "comment"),
        ("rework", "c", {}, ROOT_CAUSE.label),
        ("rework", "c", {"root_cause": "qualification"}, TARGET.label),
        ("terminate", None, {}, REASON.label),
        ("exception", "c", {"reason": "r"}, "waiver_owner"),
        ("pass", None, {}, "risk_tier"),
    ],
)
def test_a_missing_input_is_named(
    action: str, comment: str | None, fields: dict[str, str], names: str
) -> None:
    assert names in _refused(_read(action, comment, **fields), "missing_input")


@pytest.mark.parametrize(
    ("fields", "allowed"),
    [
        ({"root_cause": "defect"}, "requirement"),
        ({"root_cause": "qualification", "target_terminal": "T7"}, "T0"),
    ],
)
def test_an_invalid_input_names_what_is_allowed(fields: dict[str, str], allowed: str) -> None:
    assert allowed in _refused(_read("rework", "c", **fields), "invalid_input")


def test_limits() -> None:
    _refused(_read("rework", "x" * 4001, root_cause="requirement"), "invalid_input")
    message = _refused(_read("terminate", "c", reason="r" * 2001), "invalid_input")
    assert "waiver_owner" in _refused(
        _read("exception", "c", reason="r", values="expiry: 2030-01-01"), "missing_input"
    )
    assert "2000" in message


def test_terminate_takes_a_comment_or_a_reason() -> None:
    assert _ok(_read("terminate", "no longer needed")).comment == "no longer needed"
    assert _ok(_read("terminate", reason="duplicate")).reason == "duplicate"


def test_waiver_and_escalation_need_nothing_more() -> None:
    assert _ok(_read("approve_waiver")).comment is None
    assert _ok(_read("complete_escalation", "done")).comment == "done"


def test_a_malformed_values_line() -> None:
    _refused(_read("pass", values="risk_tier high"), "invalid_input")
