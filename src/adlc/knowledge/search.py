"""Keyword search over document sections (BM25) and section reads (008 research R-06)."""

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from adlc.knowledge.documents import SEPARATOR, Document, Section

MAX_LIMIT = 10
SNIPPET_MAX = 1000
READ_MAX = 8000
K1 = 1.5
B = 0.75
WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return WORD.findall(text.lower())


@dataclass(frozen=True)
class Hit:
    document: Document
    section: Section
    score: float

    @property
    def snippet(self) -> str:
        return self.section.text[:SNIPPET_MAX]


@dataclass(frozen=True)
class Read:
    text: str
    cut: bool
    content_hash: str


class Index:
    def __init__(self, documents: Sequence[Document]) -> None:
        self.documents = list(documents)
        self.entries: list[tuple[Document, Section, Counter[str], int]] = []
        for doc in self.documents:
            for section in doc.sections:
                words = tokens(f"{doc.title} {section.section} {section.text}")
                self.entries.append((doc, section, Counter(words), len(words)))
        self.average = sum(e[3] for e in self.entries) / len(self.entries) if self.entries else 0
        frequency: Counter[str] = Counter()
        for entry in self.entries:
            frequency.update(entry[2].keys())
        n = len(self.entries)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in frequency.items()}

    def search(self, query: str, allowed: Callable[[Document], bool], limit: int) -> list[Hit]:
        terms = set(tokens(query))
        hits = []
        for doc, section, counts, length in self.entries:
            if not allowed(doc):
                continue
            score = 0.0
            for term in terms & counts.keys():
                tf = counts[term]
                norm = tf + K1 * (1 - B + B * length / (self.average or 1))
                score += self.idf[term] * tf * (K1 + 1) / norm
            if score > 0:
                hits.append(Hit(doc, section, score))
        hits.sort(key=lambda h: (-h.score, h.document.source, h.document.path, h.section.section))
        return hits[: max(1, min(limit, MAX_LIMIT))]

    def document(self, source: str, path: str) -> Document | None:
        return next((d for d in self.documents if d.source == source and d.path == path), None)


def read_section(doc: Document, section: str | None) -> Read | None:
    """A section's text, or the outline when no section is named; capped at ``READ_MAX``."""
    if section is None:
        names = [s.section or "(introduction)" for s in doc.sections]
        text = f"{doc.title}\nSections:\n" + "\n".join(f"- {n}" for n in names)
        return Read(text, False, doc.sections[0].content_hash if doc.sections else "")
    found = doc.section(section)
    if found is None:
        return None
    return Read(found.text[:READ_MAX], len(found.text) > READ_MAX, found.content_hash)


__all__ = ["SEPARATOR", "Hit", "Index", "Read", "read_section"]
