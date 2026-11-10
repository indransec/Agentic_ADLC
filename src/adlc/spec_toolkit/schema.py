"""L2: JSON Schema validation (research R-03). Rules S-01 (terminals), S-02 (catalogues),
S-03 (checklists and playbook front matter).

Schemas live in the spec folder itself (``<root>/schema``), so the standard is versioned with
the specs it governs.
"""

import json
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from adlc.spec_toolkit.findings import Finding
from adlc.spec_toolkit.loader import LoadedFile
from adlc.spec_toolkit.rules import REGISTRY, Context


@cache
def _validator(path: Path) -> Draft202012Validator:
    schema: dict[str, Any] = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _pointer(error: ValidationError) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path]
    return "/" + "/".join(parts) if parts else ""


def _message(error: ValidationError) -> str:
    if error.validator == "additionalProperties":
        return error.message.replace("Additional properties are not allowed", "unknown field")
    return error.message


def _check(ctx: Context, rule_id: str, loaded: LoadedFile, schema_path: Path) -> Iterator[Finding]:
    if loaded.parse_failed:
        return
    if not schema_path.is_file():
        yield ctx.finding(rule_id, loaded.rel, "", f"schema {schema_path.name} not found")
        loaded.schema_failed = True
        return
    errors = sorted(
        _validator(schema_path).iter_errors(loaded.data), key=lambda e: list(e.absolute_path)
    )
    for error in errors:
        loaded.schema_failed = True
        yield ctx.finding(rule_id, loaded.rel, _pointer(error), _message(error))


@REGISTRY.rule("S-01", "L2", "error", "Terminal spec matches terminal.schema.json")
def s01_terminals(ctx: Context) -> Iterator[Finding]:
    schema = ctx.bundle.root / "schema" / "terminal.schema.json"
    for loaded in ctx.bundle.terminals.values():
        yield from _check(ctx, "S-01", loaded, schema)


@REGISTRY.rule("S-02", "L2", "error", "Catalogue matches its schema")
def s02_catalogues(ctx: Context) -> Iterator[Finding]:
    for name, loaded in ctx.bundle.catalogues.items():
        schema = ctx.bundle.root / "schema" / "catalogues" / f"{name}.schema.json"
        yield from _check(ctx, "S-02", loaded, schema)


@REGISTRY.rule(
    "S-03", "L2", "error", "Checklist, playbook and prompt front matter match their schemas"
)
def s03_checklists_playbooks(ctx: Context) -> Iterator[Finding]:
    root = ctx.bundle.root / "schema"
    for loaded in ctx.bundle.checklists.values():
        yield from _check(ctx, "S-03", loaded, root / "checklist.schema.json")
    for loaded in ctx.bundle.playbooks.values():
        yield from _check(ctx, "S-03", loaded, root / "playbook-front-matter.schema.json")
    for loaded in ctx.bundle.prompts.values():
        yield from _check(ctx, "S-03", loaded, root / "prompt-front-matter.schema.json")
