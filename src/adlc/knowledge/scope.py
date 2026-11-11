"""Grounding scope and data class rules (008 research R-03).

The platform sends a terminal's grounding scope items for one source as written in the spec. Each
item is a comma-separated list of path prefixes (starting with ``/``: a folder of the source) or
collection labels (matched case-insensitively against a document's ``collections``). An empty
scope contains nothing.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from adlc.knowledge.documents import Document


@dataclass(frozen=True)
class Scope:
    prefixes: tuple[str, ...]
    labels: frozenset[str]

    @classmethod
    def parse(cls, items: Iterable[str]) -> "Scope":
        prefixes: list[str] = []
        labels: set[str] = set()
        for item in items:
            for part in str(item).split(","):
                part = part.strip()
                if not part:
                    continue
                if part.startswith("/"):
                    folder = part.strip("/")
                    if folder:
                        prefixes.append(folder + "/")
                else:
                    labels.add(part.lower())
        return cls(tuple(prefixes), frozenset(labels))

    def contains(self, doc: Document) -> bool:
        if any(doc.path.startswith(p) for p in self.prefixes):
            return True
        return bool(self.labels & {c.lower() for c in doc.collections})


def class_allowed(data_class: str, max_class: str, ranks: Mapping[str, int]) -> bool:
    """A document's class must rank at or below ``max_class``; an unknown maximum allows
    nothing (fails closed)."""
    if max_class not in ranks or data_class not in ranks:
        return False
    return ranks[data_class] <= ranks[max_class]
