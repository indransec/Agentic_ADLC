# adlc.knowledge

The knowledge MCP server (feature 008; SA §13). It is the read-only grounding of the lifecycle
agents: a mock of the enterprise knowledge sources over a local document folder, with the tool
names and shapes a real server would have, so connecting real sources later is a configuration
change. Specification: `specs/008-terminal-agents-t0-t2/`; contract:
`contracts/knowledge-mcp.md`.

It runs as its own process and container (`adlc-knowledge`, service `knowledge`), and imports
nothing from the platform's orchestration, ledger, policy, agent or API code
(`tests/unit/test_knowledge_boundary.py`).

## Modules

| Module | Purpose |
| --- | --- |
| `documents.py` | Loads `<folder>/<source>/<path>.md`: front matter, sections by heading path, `sha256:` hash per section. A document without a known `data_class` is never loaded. |
| `search.py` | BM25 keyword search over sections (no dependency), and section reads with caps. |
| `scope.py` | Grounding scope items (path prefixes or collection labels) and the data class filter, which fails closed. |
| `server.py` | One MCP endpoint per source folder at `/mcp/<source>/` (MCP SDK `FastMCP`, streamable HTTP, stateless, JSON), each with `search` and `read`; `/health`; bearer token; DNS-rebinding protection. |
| `__main__.py` | `adlc-knowledge`: validates settings, loads the folder, serves. |

## Tools (per source)

| Tool | Model's arguments | Added by the platform | Returns |
| --- | --- | --- | --- |
| `search` | `query` (1–500 characters), `limit` (1–10, default 5) | `scope`, `max_class` | Results with source, document, section, title, snippet (≤ 1,000 characters), content hash, data class, synthetic flag |
| `read` | `document`, `section` (absent: the outline) | `scope`, `max_class` | The section text (≤ 8,000 characters, `cut` when shortened) with its hash |

Errors come back as tool errors: `out of scope`, `not found`, `invalid arguments`.

## Rules

- **Scope.** The platform sends the terminal's grounding items for the source, as written in
  the pinned spec. An item starting with `/` is a folder of the source; any other item is a
  collection label matched against a document's `collections`. No items: nothing in scope.
- **Data class.** A document is returned only if its class ranks at or below `max_class`
  (`adlc-specs/shared/data_classes.yaml`); an unknown maximum allows nothing.
- **Defence in depth.** The orchestrator's tool gate authorizes every call with feature 004 first
  (`mcp:<source>:read` against the terminal's tool scopes); the server enforces scope and class
  again. The model can set neither.
- **Security.** `ADLC_KNOWLEDGE_TOKEN` (at least 16 characters) is required for every MCP
  request; the server refuses to start without it. Host headers must match
  `ADLC_KNOWLEDGE_ALLOWED_HOSTS`. Logs hold request counts only, never content.

## Settings

`ADLC_KNOWLEDGE_DIR` (folder), `ADLC_KNOWLEDGE_TOKEN`, `ADLC_SPEC_DIR` (data class catalogue),
`ADLC_KNOWLEDGE_PORT` (8020), `ADLC_KNOWLEDGE_ALLOWED_HOSTS`, `ADLC_LOG_LEVEL`.
