"""011 T009: the package suite CI runs answers smoke and golden cases from a built package and
reports what it observed."""

from pathlib import Path

from pilot_tools.build import build, extract
from pilot_tools.package_suite import run
from tests.conftest import DEFAULT_FILL, TEMPLATE


def test_suite_counts_and_signals(tmp_path: Path) -> None:
    built = build(TEMPLATE, DEFAULT_FILL, tmp_path / "registry")
    root = extract(tmp_path / "registry", built.package_hash, tmp_path / "package")
    report = run(root, built.package_hash)
    assert report["total_count"] == 25 and report["failed_count"] == 0
    signals = {o["signal"]: o for o in report["observability"]}
    assert signals["rai_metrics"]["emitting"] is True
    assert signals["traces"]["sample_trace_id"].startswith("INC-")
