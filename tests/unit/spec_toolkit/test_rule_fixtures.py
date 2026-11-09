"""Every negative fixture is caught by its rule (SC-002); the valid bundle is clean.

Fixtures live in tests/fixtures/specs/<name>/ (patch.yaml + expected.yaml), see
tests/support/spec_fixtures.py.
"""

from pathlib import Path

import pytest

from adlc.spec_toolkit.loader import load_bundle
from adlc.spec_toolkit.rules import Context, validate
from tests.support.spec_fixtures import build_bundle, expected_findings, fixture_names


def test_valid_bundle_has_no_errors_or_warnings(tmp_path: Path) -> None:
    findings = validate(Context(load_bundle(build_bundle(tmp_path))))
    problems = [f for f in findings if f.severity in ("error", "warning")]
    assert problems == [], "\n".join(f"{f.location()} {f.rule_id} {f.message}" for f in problems)


@pytest.mark.parametrize("fixture", fixture_names())
def test_fixture_is_caught(tmp_path: Path, fixture: str) -> None:
    findings = validate(Context(load_bundle(build_bundle(tmp_path, fixture))))
    for expected in expected_findings(fixture):
        matches = [
            f
            for f in findings
            if f.rule_id == expected.rule_id
            and (expected.file is None or f.file == expected.file)
            and (expected.path_contains is None or expected.path_contains in f.path)
            and (expected.severity is None or f.severity == expected.severity)
        ]
        assert matches, f"{fixture}: expected {expected}; got\n" + "\n".join(
            f"  {f.location()} {f.rule_id} {f.path} {f.message}" for f in findings
        )
