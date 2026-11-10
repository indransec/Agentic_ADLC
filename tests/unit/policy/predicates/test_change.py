"""T023: change classification predicates over the real change class catalogue and T9 spec."""

from typing import Any

from tests.unit.policy.conftest import Check, fails, passes


def _t9(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"T9": {"change_impact_assessment": rows}}


def test_reentry_consistent(check: Check, registry: Any) -> None:
    spec = registry.entry("T9").spec
    passes(
        check(
            "reentry_consistent(T9.change_impact_assessment)",
            _t9([{"change_class": "moderate", "reentry_terminal": "T2"}]),
            terminal="T9",
            spec=spec,
        )
    )
    passes(
        check(
            "reentry_consistent(T9.change_impact_assessment)",
            _t9([{"change_class": "minor", "reentry_terminal": "T1"}]),
            terminal="T9",
            spec=spec,
        )
    )
    fails(
        check(
            "reentry_consistent(T9.change_impact_assessment)",
            _t9([{"change_class": "major", "reentry_terminal": "T3"}]),
            terminal="T9",
            spec=spec,
        ),
        "re-entry T3 is later than T1 for major",
    )
    fails(
        check(
            "reentry_consistent(T9.change_impact_assessment)",
            _t9([{"change_class": "tiny", "reentry_terminal": "T3"}]),
            terminal="T9",
            spec=spec,
        ),
        "'tiny' is not a change class",
    )


def test_class_at_least_if(check: Check) -> None:
    ok_rows = [{"change_class": "major", "affected_components": "autonomy, prompts"}]
    low_rows = [{"change_class": "minor", "affected_components": "Model; prompts"}]
    passes(
        check(
            'class_at_least_if(T9.change_impact_assessment, ["autonomy", "data_class"], "major")',
            _t9(ok_rows),
        )
    )
    fails(
        check(
            'class_at_least_if(T9.change_impact_assessment, ["model", "tool"], "moderate")',
            _t9(low_rows),
        ),
        "['model'] changed, class below moderate",
    )
    passes(
        check(
            'class_at_least_if(T9.change_impact_assessment, ["autonomy"], "major")', _t9(low_rows)
        )
    )


def test_disputed_and_has_class(check: Check) -> None:
    two = [{"change_class": "minor"}, {"change_class": "major"}]
    passes(check("classification_disputed(T9.change_impact_assessment)", _t9(two)))
    fails(
        check("classification_disputed(T9.change_impact_assessment)", _t9(two[:1])),
        "one change class",
    )
    passes(check('has_change_class(T9.change_impact_assessment, "major")', _t9(two)))
    fails(
        check('has_change_class(T9.change_impact_assessment, "emergency")', _t9(two)),
        "no emergency change",
    )
