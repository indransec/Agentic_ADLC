"""L1: load the spec folder into a SpecBundle with a location index (research R-04).

Layout (contracts/spec-files.md): ``terminals/T<n>.yaml``, ``shared/<catalogue>.yaml``,
``checklists/t<n>.yaml``, ``playbooks/**/*.md`` with YAML front matter.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError, YAMLError

from adlc.spec_toolkit.findings import Finding

FileKind = Literal["terminal", "catalogue", "checklist", "playbook", "prompt"]

# The catalogue set is part of the spec standard (FR-004), not lifecycle data.
REQUIRED_CATALOGUES: tuple[str, ...] = (
    "roles",
    "risk_tiers",
    "events",
    "root_causes",
    "change_classes",
    "data_classes",
    "model_tiers",
    "mcp_servers",
    "permissions",
    "evidence_sources",
    "route_destinations",
    "predicates",
    "metrics",
    "guardrails",
    "model_catalogue",  # feature 006
    "agents",  # feature 006
)
TERMINAL_FILE = re.compile(r"^T[0-9]+\.yaml$")
CHECKLIST_FILE = re.compile(r"^t[0-9]+\.yaml$")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)

Location = tuple[int | None, int | None]


@dataclass
class LoadedFile:
    rel: str
    kind: FileKind
    text: str
    data: Any = None
    body: str = ""
    parse_failed: bool = False
    schema_failed: bool = False
    index: dict[str, tuple[int, int]] = field(default_factory=dict)


@dataclass
class SpecBundle:
    root: Path
    terminals: dict[str, LoadedFile] = field(default_factory=dict)
    catalogues: dict[str, LoadedFile] = field(default_factory=dict)
    checklists: dict[str, LoadedFile] = field(default_factory=dict)
    playbooks: dict[str, LoadedFile] = field(default_factory=dict)
    prompts: dict[str, LoadedFile] = field(default_factory=dict)  # feature 006
    findings: list[Finding] = field(default_factory=list)

    def files(self) -> list[LoadedFile]:
        return [
            *self.catalogues.values(),
            *self.terminals.values(),
            *self.checklists.values(),
            *self.playbooks.values(),
            *self.prompts.values(),
        ]

    def file(self, rel: str) -> LoadedFile | None:
        for loaded in self.files():
            if loaded.rel == rel:
                return loaded
        return None

    def location(self, rel: str, pointer: str) -> Location:
        loaded = self.file(rel)
        if loaded is None:
            return (None, None)
        probe = pointer
        while True:
            if probe in loaded.index:
                return loaded.index[probe]
            if probe in ("", "/"):
                return (None, None)
            probe = probe.rsplit("/", 1)[0]
            if probe == "":
                return (None, None)

    def catalogue_data(self, name: str) -> dict[str, Any]:
        loaded = self.catalogues.get(name)
        if loaded is None or loaded.parse_failed or not isinstance(loaded.data, dict):
            return {}
        return loaded.data

    def usable_terminals(self) -> list[LoadedFile]:
        return [
            t
            for t in self.terminals.values()
            if not t.parse_failed and not t.schema_failed and isinstance(t.data, dict)
        ]


def _plain(node: Any) -> Any:
    if isinstance(node, dict):
        return {str(k): _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    if isinstance(node, bool) or node is None:
        return node
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        return float(node)
    if isinstance(node, datetime | date):
        return node.isoformat()
    return str(node)


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _index(node: Any, pointer: str, out: dict[str, tuple[int, int]]) -> None:
    if isinstance(node, CommentedMap):
        for key, value in node.items():
            child = f"{pointer}/{_escape(str(key))}"
            try:
                line, col = node.lc.key(key)
                out[child] = (line + 1, col + 1)
            except (KeyError, TypeError):
                pass
            _index(value, child, out)
    elif isinstance(node, CommentedSeq):
        for i, value in enumerate(node):
            child = f"{pointer}/{i}"
            try:
                line, col = node.lc.item(i)
                out[child] = (line + 1, col + 1)
            except (KeyError, TypeError, IndexError):
                pass
            _index(value, child, out)


def _p01(rel: str, exc: Exception) -> Finding:
    line = col = None
    message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    if isinstance(exc, MarkedYAMLError) and exc.problem_mark is not None:
        line, col = exc.problem_mark.line + 1, exc.problem_mark.column + 1
        message = exc.problem or message
    return Finding("P-01", "L1", "error", rel, "", line, col, f"cannot parse: {message}")


def _p02(rel: str, message: str) -> Finding:
    return Finding("P-02", "L1", "error", rel, "", None, None, message)


def _parse(yaml: YAML, loaded: LoadedFile, source: str, findings: list[Finding]) -> None:
    try:
        raw = yaml.load(source)
    except (YAMLError, ValueError) as exc:
        loaded.parse_failed = True
        findings.append(_p01(loaded.rel, exc))
        return
    loaded.data = _plain(raw)
    _index(raw, "", loaded.index)


def load_bundle(root: Path) -> SpecBundle:
    root = root.resolve()
    bundle = SpecBundle(root=root)
    yaml = YAML()  # round-trip: keeps line/column marks

    def rel(path: Path) -> str:
        return path.relative_to(root).as_posix()

    for path in sorted((root / "terminals").glob("*.yaml")):
        if not TERMINAL_FILE.match(path.name):
            bundle.findings.append(
                _p02(rel(path), f"{rel(path)}: terminal files are named T<n>.yaml")
            )
            continue
        loaded = LoadedFile(rel(path), "terminal", path.read_text())
        _parse(yaml, loaded, loaded.text, bundle.findings)
        bundle.terminals[loaded.rel] = loaded

    for name in REQUIRED_CATALOGUES:
        path = root / "shared" / f"{name}.yaml"
        if not path.is_file():
            bundle.findings.append(_p02(f"shared/{name}.yaml", f"shared/{name}.yaml missing"))
            continue
        loaded = LoadedFile(rel(path), "catalogue", path.read_text())
        _parse(yaml, loaded, loaded.text, bundle.findings)
        if not loaded.parse_failed:
            declared = loaded.data.get("catalogue") if isinstance(loaded.data, dict) else None
            if declared != name:
                bundle.findings.append(
                    _p02(
                        loaded.rel, f"{loaded.rel}: 'catalogue' must be {name!r}, got {declared!r}"
                    )
                )
        bundle.catalogues[name] = loaded
    for path in sorted((root / "shared").glob("*.yaml")):
        if path.stem not in REQUIRED_CATALOGUES:
            bundle.findings.append(_p02(rel(path), f"{rel(path)}: unknown catalogue file"))

    for path in sorted((root / "checklists").glob("*.yaml")):
        if not CHECKLIST_FILE.match(path.name):
            bundle.findings.append(
                _p02(rel(path), f"{rel(path)}: checklist files are named t<n>.yaml")
            )
            continue
        loaded = LoadedFile(rel(path), "checklist", path.read_text())
        _parse(yaml, loaded, loaded.text, bundle.findings)
        bundle.checklists[loaded.rel] = loaded

    for path in sorted((root / "playbooks").rglob("*.md")):
        if path.name == "README.md":
            continue
        loaded = LoadedFile(rel(path), "playbook", path.read_text())
        match = FRONT_MATTER.match(loaded.text)
        if match is None:
            loaded.parse_failed = True
            bundle.findings.append(
                Finding("P-01", "L1", "error", loaded.rel, "", 1, 1, "missing YAML front matter")
            )
        else:
            _parse(yaml, loaded, match.group(1), bundle.findings)
            loaded.body = match.group(2)
        bundle.playbooks[loaded.rel] = loaded

    for path in sorted((root / "prompts").glob("*.md")):
        if path.name == "README.md":
            continue
        loaded = LoadedFile(rel(path), "prompt", path.read_text())
        match = FRONT_MATTER.match(loaded.text)
        if match is None:
            loaded.parse_failed = True
            bundle.findings.append(
                Finding("P-01", "L1", "error", loaded.rel, "", 1, 1, "missing YAML front matter")
            )
        else:
            _parse(yaml, loaded, match.group(1), bundle.findings)
            loaded.body = match.group(2)
        bundle.prompts[loaded.rel] = loaded
    return bundle
