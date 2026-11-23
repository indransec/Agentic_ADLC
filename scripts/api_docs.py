# ruff: noqa: E501  # the overview holds Markdown table rows, which cannot wrap
"""``make api-docs``: write ``docs/api-reference.md`` from the platform API's OpenAPI document.

Run with ``uv run python -m scripts.api_docs [path]`` from the repository root. The reference is
generated, never edited by hand: each operation's contract lives in ``src/adlc/api/docs.py`` (what
it is for, who may call it, how it can refuse), its inputs in the route's request models, and its
answers in ``src/adlc/api/schemas/``. ``tests/unit/api/test_api_docs_fresh.py`` fails when the
committed reference is stale.
"""

import re
import sys
from pathlib import Path
from typing import Any

from scripts.export_openapi import REPO_ROOT, openapi_document

DOCUMENT = REPO_ROOT / "docs" / "api-reference.md"
REF = "#/components/schemas/"

OVERVIEW = """\
## Overview

### Where the API is

| Who | Base address |
| --- | --- |
| The browser application | `/api` on the web application's own address (`adlc-web` forwards it, unchanged) |
| Tools, tests, pilot processes | The API directly: `http://api:8000` in compose, `http://127.0.0.1:8000` locally |

Every path below is relative to the base. The API never answers CORS: a page on another origin
cannot call it from a browser.

### Sessions

Every operation needs a session except `GET /health` and `POST /auth/sign-in`.

- **Bearer** (tools, tests, pilot processes): sign in without `session` (or with `"bearer"`), then
  send `Authorization: Bearer <token>`.
- **Cookie** (the browser application): sign in with `"session": "cookie"` and the header
  `X-ADLC-CSRF: sign-in`. The answer sets the HttpOnly, SameSite=Strict cookie `adlc_session` and
  carries `csrf_token`; `GET /auth/me` also gives it. Every changing request (not GET, HEAD or
  OPTIONS) made with the cookie must send that value in `X-ADLC-CSRF`, or it is refused with `403`.
  Page scripts never see the session itself.
- A bearer header wins when both are present. Sessions expire after `ADLC_SESSION_TTL`; sign-out
  revokes them.

### Who acts

Always the signed-in person. A body that names an actor, account or role is refused (`422`).
Decision rights come from the pinned terminal specs and the role catalogue, and are checked on
every operation: hiding an action in a client is a convenience, never the control.

### Versions

Decisions, artifact edits, uploads, attachments and escalation completion send
`expected_version`: the run version the person saw (`run.version` in the run detail). If the run
changed meanwhile the answer is `409` with `kind` `stale`, and nothing is recorded; reload the run
and act again.

### Errors

Every refusal has one shape, [`ErrorBody`](#schema-errorbody):
`{"kind": "...", "detail": "...", "field": "..."}` (`field` only when one input is at fault).
Never a stack trace.

| Status | `kind` | Meaning |
| --- | --- | --- |
| 401 | `not_signed_in` | No session, or it expired or was revoked |
| 403 | `not_allowed` | The person may not do this; or a cookie session's change came without its CSRF value (`cross-site request refused`) |
| 404 | `not_found` | No such use case, run, request, event or file |
| 409 | `stale` | The run changed since the version sent |
| 409 | `wrong_state` | Not possible in the current state, or already decided |
| 422 | `invalid` | The input was refused |

Each operation lists the statuses it can answer.

### Conventions

- **Run ids contain `/`** (`UC-0001/T1/run-1`). In a path they may be sent as is or encoded
  (`UC-0001%2FT1%2Frun-1`).
- **Times** are ISO 8601 in UTC.
- **Money** (`cost_usd` in run and use-case costs) is a decimal string, such as `"0.0125"`.
- **Values from specs and catalogues** (outcomes, root causes, terminal ids, roles, states) are
  plain strings: the platform names none of them in code.
- **Text written by people or agents** (intake, comments, reasons, findings, answers, file names,
  artifact cells) is data. Clients must show it as text, never as markup.
"""


def anchor(prefix: str, text: str) -> str:
    return f"{prefix}-" + re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def schema_link(name: str) -> str:
    return f"[`{name}`](#{anchor('schema', name)})"


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def type_of(schema: dict[str, Any]) -> str:
    """A schema's type in words, with links to named schemas."""
    if "$ref" in schema:
        return schema_link(schema["$ref"].removeprefix(REF))
    if "const" in schema:
        return f"`{schema['const']!r}`".replace("'", '"')
    if "enum" in schema:
        return " or ".join(f'`"{v}"`' for v in schema["enum"])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"]
            words = " or ".join(type_of(o) for o in options) or "null"
            nullable = any(o.get("type") == "null" for o in schema[key])
            return f"{words} or null" if nullable else words
    kind = schema.get("type")
    if kind == "array":
        return f"array of {type_of(schema.get('items', {}))}"
    if kind == "object" or "additionalProperties" in schema:
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict) and extra:
            return f"object (string → {type_of(extra)})"
        return "object"
    if kind == "string" and (schema.get("format") == "binary" or "contentMediaType" in schema):
        return "file"
    if kind == "string" and schema.get("format"):
        return f"string ({schema['format']})"
    if kind == "integer":
        return "integer"
    if isinstance(kind, str):
        return kind
    return "any JSON"


def limits(schema: dict[str, Any]) -> str:
    notes = []
    for key, word in (
        ("minLength", "at least {} characters"),
        ("maxLength", "at most {} characters"),
        ("minItems", "at least {} items"),
        ("maxItems", "at most {} items"),
        ("minimum", "≥ {}"),
        ("maximum", "≤ {}"),
        ("exclusiveMinimum", "> {}"),
        ("exclusiveMaximum", "< {}"),
    ):
        value = schema.get(key)
        if value is None:
            for option in schema.get("anyOf", []):
                value = option.get(key, value)
        if value is not None:
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            notes.append(word.format(value))
    if "default" in schema and schema["default"] not in (None, [], {}):
        notes.append(
            f"default `{schema['default']}`".replace("True", "true").replace("False", "false")
        )
    return "; ".join(notes)


def fields_table(schema: dict[str, Any]) -> list[str]:
    properties: dict[str, Any] = schema.get("properties", {})
    if not properties:
        extra = schema.get("additionalProperties")
        kind = "any keys" if extra in (None, True, {}) else f"keys → {type_of(extra)}"
        return [f"An object with {kind}.", ""]
    required = set(schema.get("required", []))
    lines = ["| Field | Type | Required | Description |", "| --- | --- | --- | --- |"]
    for name, field in properties.items():
        words = field.get("description", "")
        note = limits(field)
        text = f"{words} ({note})" if words and note else words or note
        lines.append(
            f"| `{name}` | {cell(type_of(field))} | {'yes' if name in required else 'no'} | "
            f"{cell(text)} |"
        )
    if schema.get("additionalProperties") is True:
        lines.append("| *other keys* | any JSON | no | Kept as recorded |")
    return [*lines, ""]


def operation_section(
    path: str, method: str, op: dict[str, Any], schemas: dict[str, Any]
) -> list[str]:
    title = f"{method.upper()} {path}"
    out = [
        f'<a id="{anchor("op", title)}"></a>',
        "",
        f"### `{title}`",
        "",
        f"**{op['summary']}.**",
        "",
    ]
    out += [op.get("description", ""), ""]
    params = op.get("parameters", [])
    if params:
        out += [
            "**Parameters**",
            "",
            "| Name | In | Type | Required | Description |",
            "| --- | --- | --- | --- | --- |",
        ]
        for p in params:
            schema = p.get("schema", {})
            note = limits(schema)
            words = p.get("description", "")
            text = f"{words} ({note})" if words and note else words or note
            out.append(
                f"| `{p['name']}` | {p['in']} | {cell(type_of(schema))} | "
                f"{'yes' if p.get('required') else 'no'} | {cell(text)} |"
            )
        out.append("")
    body = op.get("requestBody")
    if body:
        for media, content in body.get("content", {}).items():
            schema = content.get("schema", {})
            name = schema.get("$ref", "").removeprefix(REF)
            out += [
                f"**Request body** (`{media}`{', required' if body.get('required') else ''})",
                "",
            ]
            target = schemas.get(name, schema)
            if name.startswith("Body_"):  # FastAPI's generated multipart form: show its fields
                out += fields_table(target)
            else:
                out += [f"{type_of(schema)}", ""]
                out += fields_table(target)
    out += ["**Answers**", "", "| Status | Body | Meaning |", "| --- | --- | --- |"]
    for status, answer in sorted(op.get("responses", {}).items()):
        content = answer.get("content", {})
        if not content:
            body_text = "none"
        else:
            media, value = next(iter(content.items()))
            schema = value.get("schema")
            body_text = f"{type_of(schema)} (`{media}`)" if schema else f"`{media}`"
        out.append(f"| {status} | {cell(body_text)} | {cell(answer.get('description', ''))} |")
    return [*out, ""]


def render(document: dict[str, Any]) -> str:
    schemas: dict[str, Any] = document["components"]["schemas"]
    tags = [t["name"] for t in document.get("tags", [])]
    tag_words = {t["name"]: t.get("description", "") for t in document.get("tags", [])}
    by_tag: dict[str, list[tuple[str, str, dict[str, Any]]]] = {t: [] for t in tags}
    for path, operations in document["paths"].items():
        for method, op in operations.items():
            by_tag.setdefault(op["tags"][0], []).append((path, method, op))
    lines = [
        "# Platform API reference",
        "",
        f"{document['info']['title']}, version {document['info']['version']}.",
        "",
        "> Generated from the API's OpenAPI document by `make api-docs` "
        "(`scripts/api_docs.py`); do not edit by hand. Each operation's contract is in `src/adlc/api/docs.py`, its inputs in "
        "the route's request models, its answers in `src/adlc/api/schemas/`. The same document "
        "gives the web application its types (`web/src/api/openapi.json`).",
        "",
        OVERVIEW,
        "## Operations",
        "",
        "| Area | Operation | What it does |",
        "| --- | --- | --- |",
    ]
    for tag in by_tag:
        for path, method, op in by_tag[tag]:
            title = f"{method.upper()} {path}"
            lines.append(f"| {tag} | [`{title}`](#{anchor('op', title)}) | {cell(op['summary'])} |")
    lines.append("")
    for tag, operations in by_tag.items():
        lines += [f"## {tag}", "", tag_words.get(tag, ""), ""]
        for path, method, op in operations:
            lines += operation_section(path, method, op, schemas)
    lines += [
        "## Schemas",
        "",
        "The bodies the operations take and answer, in alphabetical order.",
        "",
    ]
    for name in sorted(schemas):
        if name.startswith("Body_"):
            continue  # multipart forms are shown with their operation
        schema = schemas[name]
        lines += [f'<a id="{anchor("schema", name)}"></a>', "", f"### `{name}`", ""]
        if schema.get("description"):
            lines += [" ".join(schema["description"].split()), ""]
        if schema.get("type") == "object" or "properties" in schema:
            lines += fields_table(schema)
        else:
            lines += [f"{type_of(schema)}.", ""]
    return "\n".join(line.rstrip() for line in lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    target = Path(argv[0]) if argv else DOCUMENT
    target.write_text(render(openapi_document()))
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
