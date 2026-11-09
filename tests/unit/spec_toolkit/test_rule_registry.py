"""T011: rule registry and run order."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from adlc.spec_toolkit import rules
from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.loader import LoadedFile, SpecBundle
from adlc.spec_toolkit.rules import Context, Registry


def _bundle(tmp_path: Path, *, broken: bool = False) -> SpecBundle:
    bundle = SpecBundle(root=tmp_path)
    good = LoadedFile("terminals/T0.yaml", "terminal", "", data={"terminal": {}})
    bundle.terminals[good.rel] = good
    if broken:
        bad = LoadedFile("terminals/T1.yaml", "terminal", "", parse_failed=True)
        bundle.terminals[bad.rel] = bad
    return bundle


def test_duplicate_ids_refused() -> None:
    registry = Registry()

    @registry.rule("X-01", "L3", "error", "first")
    def first(ctx: Context) -> Iterator[Finding]:
        yield from ()

    with pytest.raises(ValueError, match="X-01"):

        @registry.rule("X-01", "L4", "error", "again")
        def again(ctx: Context) -> Iterator[Finding]:
            yield from ()


def test_runs_in_level_order_and_skips_failed_files(tmp_path: Path) -> None:
    registry = Registry()
    seen: list[str] = []

    @registry.rule("X-04", "L4", "error", "l4")
    def l4(ctx: Context) -> Iterator[Finding]:
        seen.append("L4")
        for t in ctx.terminals():
            yield ctx.finding("X-04", t.rel, "/terminal", "l4 saw " + t.rel)

    @registry.rule("X-03", "L3", "warning", "l3")
    def l3(ctx: Context) -> Iterator[Finding]:
        seen.append("L3")
        yield from ()

    findings = registry.run(Context(_bundle(tmp_path, broken=True)))
    assert seen == ["L3", "L4"]
    l4_findings = [f for f in findings if f.rule_id == "X-04"]
    assert [f.file for f in l4_findings] == ["terminals/T0.yaml"]
    assert l4_findings[0].level == "L4" and l4_findings[0].severity == "error"
    skipped = [f for f in findings if f.rule_id == "P-03"]
    assert [(f.file, f.severity) for f in skipped] == [("terminals/T1.yaml", "info")]


def test_default_registry_has_documented_shape() -> None:
    for rule in rules.REGISTRY.all():
        assert rule.level in ("L1", "L2", "L3", "L4", "L5")
        assert rule.severity in ("error", "warning", "info")
        assert rule.summary
