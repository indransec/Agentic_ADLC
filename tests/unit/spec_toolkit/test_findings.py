"""T005: findings model and reporters (contracts/adlc-spec-cli.md)."""

import json

from adlc.spec_toolkit.findings import Finding, Report


def _f(rule: str, sev: str, file: str, line: int | None = None) -> Finding:
    return Finding(
        rule_id=rule,
        level="L4",
        severity=sev,  # type: ignore[arg-type]
        file=file,
        path="/terminal/x",
        line=line,
        column=3 if line else None,
        message=f"{rule} message",
    )


def test_has_errors_only_for_error_severity() -> None:
    assert not Report([_f("V-23", "info", "a"), _f("V-26", "warning", "a")], 1, 0.1).has_errors
    assert Report([_f("V-06", "error", "a")], 1, 0.1).has_errors


def test_text_report_sorted_with_summary() -> None:
    report = Report(
        [
            _f("V-06", "error", "b.yaml", 9),
            _f("V-26", "warning", "a.yaml"),
            _f("V-01", "error", "b.yaml", 2),
        ],
        files=3,
        seconds=0.84,
    )
    lines = report.to_text().splitlines()
    assert lines[0].startswith("a.yaml ")
    assert lines[1].startswith("b.yaml:2:3 L4 V-01 error")
    assert lines[2].startswith("b.yaml:9:3 L4 V-06 error")
    assert lines[-1] == "2 errors, 1 warnings, 0 info in 3 files (0.8 s)"


def test_min_severity_hides_lower_but_keeps_counts() -> None:
    report = Report([_f("V-23", "info", "a"), _f("V-06", "error", "a")], 1, 0.1)
    text = report.to_text(min_severity="error")
    assert "V-23" not in text
    assert "1 errors, 0 warnings, 1 info" in text


def test_json_report_shape() -> None:
    data = json.loads(Report([_f("V-06", "error", "a", 4)], 2, 0.2).to_json())
    assert data["summary"] == {"errors": 1, "warnings": 0, "info": 0, "files": 2}
    assert set(data["findings"][0]) == {
        "rule_id",
        "level",
        "severity",
        "file",
        "path",
        "line",
        "column",
        "message",
    }
