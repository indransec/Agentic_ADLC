"""014 T003 (FR-001, FR-009; research R-01): the demo script is data, validated on load."""

from pathlib import Path

import pytest

from adlc.demo.script import MOMENTS, ScriptError, load_script
from tests.support.pg import REPO_ROOT

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
    assert {m for step in script.steps for m in step.proves} == set(MOMENTS)
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
