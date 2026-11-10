"""Rule registry and validation context (research R-05).

Each rule is a function ``(ctx) -> Iterable[Finding]`` registered with a stable id, level,
severity and summary (FR-009). Rules never name terminals: they iterate over what the specs and
catalogues declare (constitution I).
"""

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from adlc.spec_toolkit.findings import Finding, Level, Severity
from adlc.spec_toolkit.loader import LoadedFile, SpecBundle

_LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


@dataclass
class Context:
    """Everything a rule may read. Options steer L5 baselines."""

    bundle: SpecBundle
    baseline_ref: str | None = None
    use_git_baseline: bool = False
    registry: "Registry | None" = None
    cache: dict[str, Any] = field(default_factory=dict)

    def terminals(self) -> list[LoadedFile]:
        return self.bundle.usable_terminals()

    def catalogue(self, name: str) -> dict[str, Any]:
        return self.bundle.catalogue_data(name)

    def finding(
        self,
        rule_id: str,
        file: str,
        pointer: str,
        message: str,
        severity: Severity | None = None,
    ) -> Finding:
        registry = self.registry or REGISTRY
        rule = registry.get(rule_id)
        line, col = self.bundle.location(file, pointer)
        return Finding(
            rule_id=rule_id,
            level=rule.level,
            severity=severity or rule.severity,
            file=file,
            path=pointer,
            line=line,
            column=col,
            message=message,
        )

    def memo(self, key: str, build: Callable[[], Any]) -> Any:
        if key not in self.cache:
            self.cache[key] = build()
        return self.cache[key]


RuleCheck = Callable[[Context], Iterable[Finding]]


@dataclass(frozen=True)
class Rule:
    id: str
    level: Level
    severity: Severity
    summary: str
    check: RuleCheck


class Registry:
    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def rule(
        self, rule_id: str, level: Level, severity: Severity, summary: str
    ) -> Callable[[RuleCheck], RuleCheck]:
        def register(check: RuleCheck) -> RuleCheck:
            if rule_id in self._rules:
                raise ValueError(f"rule {rule_id} registered twice")
            self._rules[rule_id] = Rule(rule_id, level, severity, summary, check)
            return check

        return register

    def declare(self, rule_id: str, level: Level, severity: Severity, summary: str) -> None:
        """Register a rule whose findings are produced elsewhere (e.g. by another rule)."""
        self.rule(rule_id, level, severity, summary)(lambda ctx: ())

    def get(self, rule_id: str) -> Rule:
        return self._rules[rule_id]

    def all(self) -> list[Rule]:
        return sorted(self._rules.values(), key=lambda r: (_LEVEL_ORDER[r.level], r.id))

    def run(self, ctx: Context) -> list[Finding]:
        ctx.registry = self
        findings: list[Finding] = []
        skipped_reported: set[str] = set()
        for rule in self.all():
            if _LEVEL_ORDER[rule.level] >= 3:
                for loaded in ctx.bundle.files():
                    failed = loaded.parse_failed or loaded.schema_failed
                    if failed and loaded.rel not in skipped_reported:
                        skipped_reported.add(loaded.rel)
                        findings.append(
                            Finding(
                                "P-03",
                                "L1",
                                "info",
                                loaded.rel,
                                "",
                                None,
                                None,
                                f"{loaded.rel}: L3–L5 checks skipped (earlier errors)",
                            )
                        )
            findings.extend(rule.check(ctx))
        return findings


REGISTRY = Registry()

_RULE_MODULES = (
    "adlc.spec_toolkit.schema",
    "adlc.spec_toolkit.rules.single_spec",
    "adlc.spec_toolkit.rules.cross_spec",
    "adlc.spec_toolkit.rules.versioning",
    "adlc.spec_toolkit.rules.agents",
)


def load_rule_modules() -> None:
    for module in _RULE_MODULES:
        importlib.import_module(module)


def validate(ctx: Context) -> list[Finding]:
    """L1 findings from loading plus every registered rule."""
    load_rule_modules()
    return [*ctx.bundle.findings, *REGISTRY.run(ctx)]


load_rule_modules()
