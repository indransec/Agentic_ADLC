"""014 T003 (FR-001, FR-009; research R-01): the demo script is data, validated on load."""

from pathlib import Path

import pytest

from adlc.demo.script import BOARD_MOMENTS, MOMENTS, ScriptError, load_script
from tests.support.db import REPO_ROOT

ROLES = {
    "business_owner",
    "product_owner",
    "release_manager",
    "data_owner",
    "qa_eval_lead",
    "risk_owner",
}
VALID = """
usecases: {main: it-service-desk}
recordings: demo/recordings
rehearsed: demo.rehearsed:replies
steps:
  - number: 1
    usecase: main
    terminal: T0
    proves: [D-1, D-2, D-3, D-4, D-5, D-6, D-7, D-8, D-9]
    say: Submit and pass
    actions:
      - {kind: submit, role: business_owner}
      - {kind: pass, fields: {risk_tier: low}}
    expect: {final_status: pass}
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "script.yaml"
    path.write_text(text)
    return path


def test_the_repository_script_is_valid() -> None:
    script = load_script(
        REPO_ROOT / "demo" / "script.yaml",
        ROLES
        | {
            "security_officer",
            "service_owner",
            "sre",
            "solution_architect",
            "engineering_lead",
            "adlc_coe",
        },
    )
    assert {m for step in script.steps for m in step.proves} == set(MOMENTS) | BOARD_MOMENTS
    assert [s.number for s in script.steps] == sorted(s.number for s in script.steps)


def test_a_valid_script(tmp_path: Path) -> None:
    script = load_script(write(tmp_path, VALID), ROLES)
    (step,) = script.steps
    assert (step.usecase, step.terminal, step.actions[0].kind, step.actions[0].role) == (
        "main",
        "T0",
        "submit",
        "business_owner",
    )
    assert step.actions[1].params == {"fields": {"risk_tier": "low"}}
    assert script.rehearsed == "demo.rehearsed:replies"


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("{kind: submit, role: business_owner}", "{kind: dance}", "step 1: unknown action dance"),
        (
            "{kind: submit, role: business_owner}",
            "{kind: submit, role: wizard}",
            "step 1: role wizard",
        ),
        ("usecase: main", "usecase: other", "step 1: use case other"),
        ("D-8, D-9]", "D-8]", "D-9 is not shown by any step"),
        (
            "expect: {final_status: pass}",
            "expect: {colour: blue}",
            "step 1: unknown expectation colour",
        ),
        ("proves: [D-1,", "proves: [D-10, D-1,", "step 1: D-10 is not a demo moment"),
    ],
)
def test_refusals_name_the_step(tmp_path: Path, old: str, new: str, message: str) -> None:
    with pytest.raises(ScriptError, match=message):
        load_script(write(tmp_path, VALID.replace(old, new)), ROLES)


# ------------------------------------------------------------------ 020 board moments

BOARD_STEPS = """
  - number: 2
    usecase: main
    terminal: T1
    proves: [D-12]
    say: A drag without the right is set back
    actions:
      - kind: board_change
        role: product_owner
        item: usecase
        field: state
        value: "T5 Trust, Risk & Assurance"
    expect: {reverted: true}
  - number: 3
    usecase: main
    terminal: T1
    proves: [D-13]
    say: Drift corrected
    actions:
      - {kind: drift, item: usecase, field: sub_stage, value: Closed}
      - {kind: reconcile}
    expect: {reconciled: true}
"""


def test_board_steps(tmp_path: Path) -> None:
    script = load_script(write(tmp_path, VALID + BOARD_STEPS), ROLES)
    d12, d13 = script.steps[1:]
    assert d12.board_only and d13.board_only and not script.steps[0].board_only
    assert d12.actions[0].params == {
        "item": "usecase",
        "field": "state",
        "value": "T5 Trust, Risk & Assurance",
    }
    assert d13.expect == {"reconciled": True}
    assert {"D-12", "D-13"} == BOARD_MOMENTS


def test_a_script_without_board_moments_is_valid(tmp_path: Path) -> None:
    assert load_script(write(tmp_path, VALID), ROLES).steps  # the board moments are optional


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "item: usecase\n        field: state",
            "item: sprint\n        field: state",
            "step 2: item sprint",
        ),
        ("        field: state\n", "", "step 2: board_change needs"),
        (
            "{kind: drift, item: usecase, field: sub_stage, value: Closed}",
            "{kind: drift}",
            "step 3: drift needs",
        ),
        (
            "proves: [D-12]",
            "proves: [D-12, D-1]",
            "step 2: D-1 cannot be proved by a board-only step",
        ),
    ],
)
def test_board_step_refusals(tmp_path: Path, old: str, new: str, message: str) -> None:
    with pytest.raises(ScriptError, match=message):
        load_script(write(tmp_path, VALID + BOARD_STEPS.replace(old, new)), ROLES)


def test_board_moments_only_on_board_steps(tmp_path: Path) -> None:
    text = VALID.replace("proves: [D-1,", "proves: [D-12, D-1,")
    with pytest.raises(ScriptError, match="step 1: D-12 is shown only by a board-only step"):
        load_script(write(tmp_path, text), ROLES)
