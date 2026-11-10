"""Validation findings and reporters (contracts/adlc-spec-cli.md, data-model.md)."""

import json
from dataclasses import asdict, dataclass
from typing import Literal

Severity = Literal["error", "warning", "info"]
Level = Literal["L1", "L2", "L3", "L4", "L5"]

_RANK: dict[str, int] = {"info": 0, "warning": 1, "error": 2}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    level: Level
    severity: Severity
    file: str
    path: str
    line: int | None
    column: int | None
    message: str

    def location(self) -> str:
        if self.line is None:
            return self.file
        return f"{self.file}:{self.line}:{self.column or 1}"


@dataclass(frozen=True)
class Report:
    findings: list[Finding]
    files: int
    seconds: float

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def has_errors(self) -> bool:
        return self.count("error") > 0

    def sorted(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (f.file, f.line or 0, f.rule_id, f.path))

    def to_text(self, min_severity: Severity = "info") -> str:
        floor = _RANK[min_severity]
        lines = [
            f"{f.location()} {f.level} {f.rule_id} {f.severity:<7} {f.message}"
            for f in self.sorted()
            if _RANK[f.severity] >= floor
        ]
        lines.append(
            f"{self.count('error')} errors, {self.count('warning')} warnings, "
            f"{self.count('info')} info in {self.files} files ({self.seconds:.1f} s)"
        )
        return "\n".join(lines)

    def to_json(self, min_severity: Severity = "info") -> str:
        floor = _RANK[min_severity]
        return json.dumps(
            {
                "summary": {
                    "errors": self.count("error"),
                    "warnings": self.count("warning"),
                    "info": self.count("info"),
                    "files": self.files,
                },
                "findings": [asdict(f) for f in self.sorted() if _RANK[f.severity] >= floor],
            },
            indent=2,
        )
