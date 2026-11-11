"""Knowledge documents: front matter, sections and content hashes (008 research R-07).

A document is ``<root>/<source>/<path>.md`` with YAML front matter (``title``, ``data_class``,
``synthetic``, ``collections``, ``version``). Sections are the Markdown headings below the title;
a section's id is its heading path (``Controls > Human oversight``); the text before the first
sub-heading is the section ``""``. A document whose ``data_class`` is missing or unknown is never
loaded (it fails closed).
"""

import hashlib
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

log = logging.getLogger("adlc.knowledge")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SEPARATOR = " > "


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Section:
    section: str  # heading path; "" for the text before the first sub-heading
    text: str
    content_hash: str


@dataclass(frozen=True)
class Document:
    source: str
    path: str  # relative to the source folder, with "/" separators
    title: str
    data_class: str
    synthetic: bool
    collections: tuple[str, ...]
    version: str
    sections: tuple[Section, ...]

    def section(self, name: str) -> Section | None:
        return next((s for s in self.sections if s.section == name), None)


def _sections(body: str) -> tuple[Section, ...]:
    """Split at headings below the document title (the first level-1 heading)."""
    found: list[tuple[str, list[str]]] = [("", [])]
    stack: list[tuple[int, str]] = []
    title_seen = False
    for line in body.splitlines():
        match = HEADING.match(line)
        if match is None:
            found[-1][1].append(line)
            continue
        level, text = len(match.group(1)), match.group(2)
        if level == 1 and not title_seen:
            title_seen = True
            continue
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
        found.append((SEPARATOR.join(t for _, t in stack), [line]))
    sections = []
    for name, lines in found:
        text = "\n".join(lines).strip()
        if text:
            sections.append(Section(name, text, content_hash(text)))
    return tuple(sections)


def _front_matter(text: str) -> tuple[Mapping[str, Any], str] | None:
    match = FRONT_MATTER.match(text)
    if match is None:
        return None
    try:
        meta = YAML(typ="safe").load(match.group(1))
    except YAMLError:
        return None
    return (meta, match.group(2)) if isinstance(meta, Mapping) else None


def load_document(root: Path, path: Path, classes: Mapping[str, int]) -> Document | None:
    rel = path.relative_to(root)
    parsed = _front_matter(path.read_text(encoding="utf-8"))
    if parsed is None:
        log.warning("knowledge document without front matter skipped: %s", rel)
        return None
    meta, body = parsed
    data_class = str(meta.get("data_class") or "")
    if data_class not in classes:
        log.warning("knowledge document without a known data class skipped: %s", rel)
        return None
    collections = meta.get("collections") or []
    return Document(
        source=rel.parts[0],
        path="/".join(rel.parts[1:]),
        title=str(meta.get("title") or rel.stem),
        data_class=data_class,
        synthetic=bool(meta.get("synthetic", False)),
        collections=tuple(str(c) for c in collections) if isinstance(collections, list) else (),
        version=str(meta.get("version") or ""),
        sections=_sections(body),
    )


def load_folder(root: Path, classes: Mapping[str, int]) -> list[Document]:
    """Every loadable document under ``root/<source>/``, in path order."""
    documents = []
    for path in sorted(root.glob("*/**/*.md")):
        if path.name.lower() == "readme.md":
            continue
        loaded = load_document(root, path, classes)
        if loaded is not None:
            documents.append(loaded)
    return documents
