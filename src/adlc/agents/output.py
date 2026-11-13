"""Structured output: parsing, validation and correction messages (006 FR-013, FR-017, FR-019).

Output is validated before anything else sees it. Problems name ids, columns and positions only;
they never echo artifact content back.
"""

import json
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from adlc.agents.imports import Resolver, expand, is_import
from adlc.orchestration import spec_view
from adlc.orchestration.interfaces import Artifacts, Citation, Clarification, Recommendation

FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
SCALAR = (str, int, float, bool, type(None))
REVIEW_STATUSES = ("pass", "rework", "exception")
MAX_QUESTIONS = 5
MAX_TEXT = 1000


@dataclass(frozen=True)
class Parsed:
    result: Artifacts | Clarification | Recommendation | None = None
    tool: Mapping[str, Any] | None = None  # {"name": ..., "arguments": {...}} (US4)
    problems: tuple[str, ...] = field(default_factory=tuple)


OPENERS = {"{": "}", "[": "]"}


def balance(text: str) -> str:
    """Drop closing brackets that match no open bracket and add missing ones, outside strings
    (008: small models sometimes emit one brace too many in long answers). The result is still
    validated in full, so a wrong repair cannot pass."""
    out: list[str] = []
    stack: list[str] = []
    in_string = escaped = False
    for ch in text:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in OPENERS:
            stack.append(OPENERS[ch])
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                continue  # an unmatched closer
            stack.pop()
        out.append(ch)
    return "".join(out) + "".join(reversed(stack))


def _candidates(raw: str) -> list[str]:
    match = FENCED.search(raw)
    candidates = [match.group(1)] if match else []
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    return candidates


def json_error(raw: str) -> str:
    """Why the answer is not one JSON object, for the correction message."""
    for candidate in _candidates(raw):
        try:
            json.loads(candidate)
        except json.JSONDecodeError as exc:
            return f"the answer is not valid JSON ({exc.msg} at character {exc.pos})"
    return "the answer is not one JSON object"


def parse_json(raw: str) -> dict[str, Any] | None:
    """One JSON object from a fenced block, or the outermost braces; failing that, the same with
    unmatched brackets repaired."""
    candidates = _candidates(raw)
    for candidate in [*candidates, *(balance(c) for c in candidates)]:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def correction(problems: Sequence[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        "Your previous answer did not fit the required shape:\n"
        f"{listed}\n"
        "Answer again with one corrected JSON object only."
    )


def _clarification(
    value: Any, role_ids: Collection[str] | None
) -> tuple[Clarification | None, list[str]]:
    problems: list[str] = []
    if not isinstance(value, Mapping):
        return None, ["clarification must be an object"]
    questions = value.get("questions")
    if (
        not isinstance(questions, list)
        or not 1 <= len(questions) <= MAX_QUESTIONS
        or not all(isinstance(q, str) and q.strip() for q in questions)
    ):
        problems.append(f"clarification.questions must hold 1 to {MAX_QUESTIONS} questions")
    looked = value.get("looked_in")
    if not isinstance(looked, list) or not [x for x in looked if isinstance(x, str) and x.strip()]:
        problems.append("clarification.looked_in must list where you looked (at least one)")
    role = value.get("addressed_role")
    if role is not None and (not isinstance(role, str) or (role_ids and role not in role_ids)):
        problems.append("clarification.addressed_role must be null or a known role")
    extra = set(value) - {"questions", "looked_in", "addressed_role"}
    if extra:
        problems.append(f"clarification has unknown keys: {sorted(extra)}")
    if problems:
        return None, problems
    return (
        Clarification(
            tuple(str(q) for q in questions),  # type: ignore[union-attr]
            addressed_role=role,
            looked_in=tuple(str(x) for x in looked),  # type: ignore[union-attr]
        ),
        [],
    )


def validate_artifacts(
    artifacts: Any, spec: Mapping[str, Any], required: Callable[[spec_view.ArtifactSpec], bool]
) -> list[str]:
    """Every required artifact present, nothing undeclared, rows with exactly the columns."""
    if not isinstance(artifacts, Mapping):
        return ["artifacts must be an object keyed by artifact id"]
    declared = {a.id: a for a in spec_view.artifacts(spec)}
    problems = [
        f"artifact {aid} is not declared for this terminal"
        for aid in artifacts
        if aid not in declared
    ]
    for aid, decl in declared.items():
        rows = artifacts.get(aid)
        if decl.built:  # 011 FR-003, 012 R-09: built from records; agents never write it
            if rows is not None:
                what = (
                    "signed by people at sign-off"
                    if decl.format == SIGNED
                    else "built by the platform from records"
                )
                problems.append(f"artifact {aid} is {what}; leave it out")
            continue
        if rows is None:
            if required(decl):
                problems.append(f"artifact {aid} is missing")
            continue
        if not isinstance(rows, list) or not all(isinstance(r, Mapping) for r in rows):
            problems.append(f"artifact {aid} must be a list of rows")
            continue
        columns = set(decl.columns)
        for i, row in enumerate(rows, start=1):
            missing, extra = sorted(columns - set(row)), sorted(set(row) - columns)
            if missing:
                problems.append(f"{aid} row {i}: missing columns {missing}")
            if extra:
                problems.append(f"{aid} row {i}: unknown columns {extra}")
            if any(not isinstance(v, SCALAR) for v in row.values()):
                problems.append(f"{aid} row {i}: values must be text, numbers, true/false or null")
    return problems


SIGNED = "signed_record"
CITATION_KEYS = {"artifact", "row", "source", "document", "section"}


def _citations(
    value: Any, artifacts: Mapping[str, Any], retrieved: Sequence[Any]
) -> tuple[tuple[Citation, ...], list[str]]:
    """Optional citations (008 FR-016): each must name an answered artifact (and an existing row)
    and match a retrieval of this attempt; the hash and id come from that retrieval."""
    if not isinstance(value, list):
        return (), ["citations must be a list"]
    found: list[Citation] = []
    problems: list[str] = []
    by_key = {(r.source, r.document, r.section): r for r in retrieved}
    for i, item in enumerate(value, start=1):
        if not isinstance(item, Mapping) or set(item) - CITATION_KEYS:
            problems.append(f"citation {i} must have only {sorted(CITATION_KEYS)}")
            continue
        artifact, row = item.get("artifact"), item.get("row")
        rows = artifacts.get(artifact) if isinstance(artifact, str) else None
        if rows is None or not isinstance(artifact, str):
            problems.append(f"citation {i}: artifact must be one of the artifacts you answered")
            continue
        if row is not None and (
            not isinstance(row, int) or isinstance(row, bool) or not 0 <= row < len(rows)
        ):
            problems.append(f"citation {i}: row must be null or an existing row index")
            continue
        key = (str(item.get("source")), str(item.get("document")), str(item.get("section") or ""))
        match = by_key.get(key)
        if match is None or match.retrieval_id is None:
            problems.append(
                f"citation {i}: cite only a source, document and section you retrieved in this "
                "attempt"
            )
            continue
        found.append(
            Citation(artifact, row, key[0], key[1], key[2], match.content_hash, match.retrieval_id)
        )
    return tuple(found), problems


def parse_builder(
    raw: str,
    spec: Mapping[str, Any],
    required: Callable[[spec_view.ArtifactSpec], bool],
    role_ids: Collection[str] | None = None,
    retrievals: Callable[[], Sequence[Any]] | None = None,
    resolve: Resolver | None = None,
) -> Parsed:
    data = parse_json(raw)
    if data is None:
        return Parsed(problems=(json_error(raw),))
    keys = set(data)
    if keys == {"clarification"}:
        result, problems = _clarification(data["clarification"], role_ids)
        return Parsed(result, problems=tuple(problems))
    if keys == {"tool"}:
        tool = data["tool"]
        if isinstance(tool, Mapping) and isinstance(tool.get("name"), str):
            return Parsed(
                tool={"name": tool["name"], "arguments": dict(tool.get("arguments") or {})}
            )
        return Parsed(problems=('tool must be {"name": ..., "arguments": {...}}',))
    if keys not in ({"artifacts"}, {"artifacts", "citations"}):
        return Parsed(
            problems=(
                'the object must be {"artifacts": ...} (optionally with "citations"), '
                '{"clarification": ...} or {"tool": ...}',
            )
        )
    imported, problems = _imports(data["artifacts"], spec, resolve)
    if problems:
        return Parsed(problems=tuple(problems))
    problems = validate_artifacts(data["artifacts"], spec, required)
    if problems:
        return Parsed(problems=tuple(problems))
    cited: tuple[Citation, ...] = ()
    if "citations" in data:
        cited, problems = _citations(
            data["citations"], data["artifacts"], retrievals() if retrievals else []
        )
        if problems:
            return Parsed(problems=tuple(problems))
    rows = {k: [dict(r) for r in v] for k, v in data["artifacts"].items()}
    return Parsed(Artifacts(rows, cited, imported))


def _imports(
    artifacts: Any, spec: Mapping[str, Any], resolve: Resolver | None
) -> tuple[tuple[dict[str, Any], ...], list[str]]:
    """011: expand ``{"import": ...}`` tables in place from recorded results."""
    if not isinstance(artifacts, dict):
        return (), []
    declared = {a.id: a for a in spec_view.artifacts(spec)}
    found: list[dict[str, Any]] = []
    problems: list[str] = []
    for aid, value in list(artifacts.items()):
        if not is_import(value) or aid not in declared:
            continue
        rows, provenance, issues = expand(aid, tuple(declared[aid].columns), value, resolve)
        problems += issues
        if provenance is not None:
            artifacts[aid] = rows
            found.append(asdict(provenance))
    return tuple(found), problems


def parse_review(
    raw: str,
    item_ids: Sequence[str],
    root_causes: Collection[str],
    role_ids: Collection[str] | None = None,
) -> Parsed:
    """The reviewer's answer (contracts/reviewer.md), mapped to a ``Recommendation``."""
    data = parse_json(raw)
    if data is None:
        return Parsed(problems=(json_error(raw),))
    if set(data) == {"clarification"}:
        asked, asking_problems = _clarification(data["clarification"], role_ids)
        return Parsed(asked, problems=tuple(asking_problems))
    problems: list[str] = []
    if set(data) != {"scores", "findings", "recommendation"}:
        problems.append('the object must have exactly "scores", "findings" and "recommendation"')
        return Parsed(problems=tuple(problems))
    scores = data["scores"]
    if not isinstance(scores, Mapping):
        problems.append("scores must be an object keyed by checklist item id")
        scores = {}
    missing = [i for i in item_ids if i not in scores]
    unknown = [i for i in scores if i not in item_ids]
    if missing:
        problems.append(f"scores missing items {missing}")
    if unknown:
        problems.append(f"scores has unknown items {unknown}")
    for item, score in scores.items():
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 3:
            problems.append(f"score of {item} must be a whole number from 0 to 3")
    findings = data["findings"]
    texts: list[str] = []
    if not isinstance(findings, list):
        problems.append("findings must be a list")
        findings = []
    for i, f in enumerate(findings, start=1):
        if not isinstance(f, Mapping) or set(f) - {"item", "text"}:
            problems.append(f'finding {i} must be {{"item": ..., "text": ...}}')
            continue
        item, body = f.get("item"), f.get("text")
        if item is not None and item not in item_ids:
            problems.append(f"finding {i}: item must be null or a checklist item id")
        if not isinstance(body, str) or not 1 <= len(body.strip()) <= MAX_TEXT:
            problems.append(f"finding {i}: text must have 1 to {MAX_TEXT} characters")
            continue
        texts.append(f"{item}: {body.strip()}" if item else body.strip())
    rec = data["recommendation"]
    status = reason = root_cause = None
    if not isinstance(rec, Mapping) or set(rec) - {"status", "reason", "root_cause"}:
        problems.append('recommendation must be {"status", "reason", "root_cause"}')
    else:
        status, reason, root_cause = rec.get("status"), rec.get("reason"), rec.get("root_cause")
        if status not in REVIEW_STATUSES:
            problems.append(f"recommendation.status must be one of {list(REVIEW_STATUSES)}")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= MAX_TEXT:
            problems.append(f"recommendation.reason must have 1 to {MAX_TEXT} characters")
        if status == "rework" and root_cause not in root_causes:
            problems.append(f"recommendation.root_cause must be one of {sorted(root_causes)}")
        if status != "rework" and root_cause is not None:
            problems.append("recommendation.root_cause must be null unless the status is rework")
    if problems:
        return Parsed(problems=tuple(problems))
    return Parsed(
        Recommendation(
            str(status),
            {str(k): int(v) for k, v in scores.items()},
            tuple(texts),
            reason=str(reason).strip(),
            root_cause=None if root_cause is None else str(root_cause),
            reviewer="model",
        )
    )
