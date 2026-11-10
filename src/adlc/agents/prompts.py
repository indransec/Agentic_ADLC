"""Prompts, playbooks and checklists as agents read them (006 research R-04, R-06).

Prompts and playbooks are registered with a hash (``spec.prompt_registry``,
``spec.playbook_registry``). At run time the text is read from the spec folder and checked against
that hash; a file that changed after registration is refused rather than used silently.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ruamel.yaml import YAML
from sqlalchemy import Engine, text

from adlc.spec_toolkit.loader import FRONT_MATTER, SpecBundle
from adlc.spec_toolkit.normalise import file_hash


class SpecFileError(Exception):
    """A prompt, playbook or checklist is unknown, missing, or differs from its registration."""


@dataclass(frozen=True)
class SpecText:
    id: str
    version: str
    path: str
    hash: str
    body: str  # the text after the front matter


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    text: str


class SpecTexts(Protocol):
    def prompt(self, prompt_id: str, version: str) -> SpecText: ...

    def playbook(self, playbook_id: str, version: str) -> SpecText: ...

    def checklist(self, ref: str, version: str) -> tuple[ChecklistItem, ...]: ...


def _body(raw: str) -> str:
    match = FRONT_MATTER.match(raw)
    return raw if match is None else match.group(2)


def _checklist(raw: str, ref: str, version: str) -> tuple[ChecklistItem, ...]:
    data: Any = YAML(typ="safe").load(raw) or {}
    if str(data.get("version")) != version:
        raise SpecFileError(f"{ref}: version {data.get('version')} is not the pinned {version}")
    return tuple(
        ChecklistItem(str(i["id"]), str(i.get("text", ""))) for i in data.get("items") or []
    )


class SqlSpecTexts:
    """Registered hashes from the database; text from the spec folder (production)."""

    TABLES: Mapping[str, tuple[str, str]] = {
        "prompt": ("spec.prompt_registry", "prompt_id"),
        "playbook": ("spec.playbook_registry", "playbook_id"),
    }

    def __init__(self, engine: Engine, spec_dir: Path) -> None:
        self.engine = engine
        self.spec_dir = spec_dir

    def _load(self, kind: str, item_id: str, version: str) -> SpecText:
        table, column = self.TABLES[kind]
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    f"SELECT path, content_hash FROM {table} "  # noqa: S608 - fixed names
                    f"WHERE {column} = :i AND version = :v"
                ),
                {"i": item_id, "v": version},
            ).first()
        if row is None:
            raise SpecFileError(f"{kind} {item_id}@{version} is not registered")
        path = self.spec_dir / str(row[0])
        if not path.is_file():
            raise SpecFileError(f"{kind} {item_id}@{version}: {row[0]} not found")
        raw = path.read_text()
        if file_hash(raw) != row[1]:
            raise SpecFileError(
                f"{kind} {item_id}@{version}: {row[0]} differs from its registration"
            )
        return SpecText(item_id, version, str(row[0]), str(row[1]), _body(raw))

    def prompt(self, prompt_id: str, version: str) -> SpecText:
        return self._load("prompt", prompt_id, version)

    def playbook(self, playbook_id: str, version: str) -> SpecText:
        return self._load("playbook", playbook_id, version)

    def checklist(self, ref: str, version: str) -> tuple[ChecklistItem, ...]:
        path = self.spec_dir / ref
        if not path.is_file():
            raise SpecFileError(f"checklist {ref} not found")
        return _checklist(path.read_text(), ref, version)


class BundleSpecTexts:
    """The same, read from a loaded spec bundle (tests and local tools)."""

    def __init__(self, bundle: SpecBundle) -> None:
        self.bundle = bundle

    def _find(self, files: Mapping[str, Any], item_id: str, version: str, kind: str) -> SpecText:
        for loaded in files.values():
            data = loaded.data if isinstance(loaded.data, dict) else {}
            if str(data.get("id")) == item_id and str(data.get("version")) == version:
                return SpecText(item_id, version, loaded.rel, file_hash(loaded.text), loaded.body)
        raise SpecFileError(f"{kind} {item_id}@{version} not found")

    def prompt(self, prompt_id: str, version: str) -> SpecText:
        return self._find(self.bundle.prompts, prompt_id, version, "prompt")

    def playbook(self, playbook_id: str, version: str) -> SpecText:
        return self._find(self.bundle.playbooks, playbook_id, version, "playbook")

    def checklist(self, ref: str, version: str) -> tuple[ChecklistItem, ...]:
        loaded = self.bundle.checklists.get(ref)
        if loaded is None:
            raise SpecFileError(f"checklist {ref} not found")
        return _checklist(loaded.text, ref, version)
