"""Build the CEL activation for one evaluation, and record what it read (FR-019, R-08).

Each referenced path is followed in the evidence. A path into a table reads the first row
(``<terminal>.<artifact>.<column>``); such a path is bound to its own variable, because CEL only
selects fields of mappings. Missing evidence is bound as an error value, so CEL's own logic
decides whether the rule needed it (contracts/policy-engine.md step 2).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from celpy import celtypes
from celpy.evaluation import CELEvalError

from adlc.policy.evidence import Answer, Evidence
from adlc.policy.predicates.context import Record, Table
from adlc.policy.values import to_cel
from adlc.spec_toolkit.normalise import content_hash

MAX_ROWS = 10_000
MAX_TEXT = 100_000


class TooLarge(Exception):
    pass


@dataclass
class Inputs:
    """What one evaluation read: per path, a summary, its source and whether it was synthetic."""

    read: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def synthetic(self) -> bool:
        return any(v.get("synthetic") for v in self.read.values())

    def add(self, path: str, value: Any, source: str, synthetic: bool) -> None:
        self.read[path] = {
            "value": summarise(path, value),
            "source": source,
            "synthetic": synthetic,
        }

    def missing(self, path: str) -> None:
        self.read.setdefault(path, {"value": None, "source": "not available", "synthetic": False})


def summarise(path: str, value: Any) -> Any:
    """Scalars in full; tables as a reference with row count and content hash (R-08)."""
    if isinstance(value, list):
        return {"ref": path, "rows": len(value), "content_hash": content_hash(value)}
    if isinstance(value, Mapping):
        return {str(k): summarise(f"{path}.{k}", v) for k, v in value.items()}
    if isinstance(value, str) and len(value) > 500:
        return {"ref": path, "chars": len(value), "content_hash": content_hash(value)}
    return value


def named(value: Any, path: str) -> Any:
    """CEL value whose tables remember their path."""
    if isinstance(value, Mapping):
        items = {celtypes.StringType(str(k)): named(v, f"{path}.{k}") for k, v in value.items()}
        return Record.named(items, path)
    if isinstance(value, list):
        if len(value) > MAX_ROWS:
            raise TooLarge(path)
        return Table.named([named(v, f"{path}[{i}]") for i, v in enumerate(value)], path)
    if isinstance(value, str) and len(value) > MAX_TEXT:
        raise TooLarge(path)
    return to_cel(value)


def missing_error(path: str) -> CELEvalError:
    return CELEvalError(f"evidence not available: {path}", KeyError, None)


@dataclass
class Activation:
    variables: dict[str, Any]
    text: str


def build(
    expression: str,
    refs: tuple[tuple[str, ...], ...],
    answers: Mapping[str, Answer],
    inputs: Inputs,
) -> Activation:
    variables: dict[str, Any] = {}
    replacements: dict[str, str] = {}
    for root in dict.fromkeys(r[0] for r in refs):
        answer = answers[root]
        if isinstance(answer, Evidence):
            variables[root] = named(answer.value, root)
        else:
            variables[root] = missing_error(root)
            inputs.missing(root)
    for ref in refs:
        answer = answers[ref[0]]
        if not isinstance(answer, Evidence):
            continue
        value: Any = answer.value
        walked = [ref[0]]
        crossed_table = False
        missing: str | None = None
        for member in ref[1:]:
            if isinstance(value, list):
                crossed_table = True
                value = value[0] if value and isinstance(value[0], Mapping) else None
            if isinstance(value, Mapping) and member in value:
                value = value[member]
                walked.append(member)
            else:
                missing = ".".join([*walked, member])
                break
        dotted = ".".join(ref)
        if missing is not None:
            inputs.missing(missing)
            if crossed_table or len(ref) > 1:
                replacements[dotted] = f"__ref{len(replacements)}"
                variables[replacements[dotted]] = missing_error(missing)
            continue
        inputs.add(dotted, value, answer.source, answer.synthetic)
        if crossed_table:
            replacements[dotted] = f"__ref{len(replacements)}"
            variables[replacements[dotted]] = named(value, dotted)
    text = expression
    for dotted in sorted(replacements, key=len, reverse=True):
        pattern = r"(?<![\w.])" + re.escape(dotted) + r"(?![\w(])"
        text = re.sub(pattern, replacements[dotted], text)
    return Activation(variables, text)
