"""The checks CI adds after a build (feature 011, research R-04, contracts/ci-report.md): the
package suite with line coverage, SAST (bandit), a secret scan, an SBOM with licence approval and
the observed telemetry signals. Each returns a check and the report section the platform's
evidence reads."""

import importlib.metadata
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

import triage_agent

AGENT_CODE = Path(triage_agent.__file__).resolve().parent
OPTIONAL_CODE = ("real.py",)  # the optional real-model client is not run by the suite
SUITE_TIMEOUT_S = 60
SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("critical", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("critical", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("critical", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    (
        "high",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{12,}"
        ),
    ),
    ("high", re.compile(r"://[^/\s:@]+:[^@\s/]+@")),
)


def check(name: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def _counts(levels: Iterable[str]) -> dict[str, int]:
    found = list(levels)
    return {f"{s}_count": found.count(s) for s in ("critical", "high", "medium")}


def package_suite(
    root: Path, package_hash: str
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Run the suite under coverage in a fresh process; returns the check, the tests section and
    the observability rows."""
    with tempfile.TemporaryDirectory() as work:
        data = Path(work) / ".coverage"
        omit = ",".join(f"*/{name}" for name in OPTIONAL_CODE)
        base = [sys.executable, "-m", "coverage"]
        run = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [
                *base,
                "run",
                f"--data-file={data}",
                f"--include={AGENT_CODE}/*",
                f"--omit={omit}",
                "-m",
                "pilot_tools.package_suite",
                str(root),
                package_hash,
            ],
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_S,
            check=False,
        )
        if run.returncode != 0:
            return check("tests", False, run.stderr[-300:]), {}, []
        suite = json.loads(run.stdout.strip().splitlines()[-1])
        report = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [*base, "json", f"--data-file={data}", "-o", "-", "-q"],
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT_S,
            check=False,
        )
        coverage = round(float(json.loads(report.stdout)["totals"]["percent_covered"]), 1)
    tests = {
        "package": {
            "total_count": suite["total_count"],
            "passed_count": suite["passed_count"],
            "failed_count": suite["failed_count"],
            "coverage_pct": coverage,
        }
    }
    ok = suite["failed_count"] == 0
    return (
        check("tests", ok, f"{suite['passed_count']}/{suite['total_count']}, coverage {coverage}%"),
        tests,
        suite["observability"],
    )


def sast() -> tuple[dict[str, Any], dict[str, int]]:
    done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        [sys.executable, "-m", "bandit", "-r", str(AGENT_CODE), "-f", "json", "-q"],
        capture_output=True,
        text=True,
        timeout=SUITE_TIMEOUT_S,
        check=False,
    )
    results = json.loads(done.stdout or "{}").get("results") or []
    counts = _counts(str(r.get("issue_severity", "")).lower() for r in results)
    clean = counts["critical_count"] == 0 and counts["high_count"] == 0
    return check("sast", clean, f"{len(results)} findings"), counts


def secret_scan(texts: dict[str, str]) -> tuple[dict[str, Any], dict[str, int]]:
    levels = [
        level for text in texts.values() for level, pattern in SECRETS if pattern.search(text)
    ]
    counts = _counts(levels)
    return check("secret_scan", not levels, f"{len(levels)} findings"), counts


def scanned_texts(root: Path) -> dict[str, str]:
    texts = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".md", ".yaml", ".yml", ".txt", ".json"):
            texts[str(path.relative_to(root))] = path.read_text(errors="replace")
    return texts


def sbom(licences_file: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = YAML(typ="safe").load(licences_file.read_text())
    approved = [str(a).lower() for a in allowed.get("approved") or []]
    own = {str(o).lower() for o in allowed.get("own") or []}
    components, unapproved = [], []
    for dist in importlib.metadata.distributions():
        meta = dist.metadata
        name = str(meta["Name"])
        licence = (
            meta.get("License-Expression")
            or "; ".join(
                c.split("::")[-1].strip()
                for c in (meta.get_all("Classifier") or [])
                if c.startswith("License ::")
            )
            or str(meta.get("License") or "")
        )
        components.append({"name": name, "version": dist.version, "licence": licence[:80]})
        if name.lower() not in own and not any(a in licence.lower() for a in approved):
            unapproved.append(name)
    report = {
        "generated": True,
        "licences_approved": not unapproved,
        "components": sorted(components, key=lambda c: c["name"].lower()),
    }
    detail = f"{len(components)} components" + (
        f"; not approved: {', '.join(sorted(unapproved))}" if unapproved else ""
    )
    return check("sbom", not unapproved, detail), report


def observability_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = bool(rows) and all(r.get("emitting") for r in rows)
    return check("observability", ok, ", ".join(f"{r['signal']}={r['emitting']}" for r in rows))
