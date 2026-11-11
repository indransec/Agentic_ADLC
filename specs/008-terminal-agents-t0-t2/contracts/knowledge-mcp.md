# Contract: Knowledge MCP Server (feature 008)

A read-only MCP server (streamable HTTP, stateless, JSON responses) over a local document folder.
It mocks the enterprise knowledge sources of the MCP catalogue with the tool names and schemas a
real server would expose (SA §13).

## Endpoints

| Path | Serves |
| --- | --- |
| `POST /mcp/<source>` | The MCP endpoint of one catalogue source that has a folder under `ADLC_KNOWLEDGE_DIR` (`confluence`, `sharepoint`, `portfolio`, `jira`, `arch_repo`, `mcp_registry`) |
| `GET /health` | `{"status": "ok", "sources": [...], "documents": n}`; no token needed |

Every MCP request needs `Authorization: Bearer <ADLC_KNOWLEDGE_TOKEN>`. Without it the answer is
401.

## Tools (per source)

### `search`

| Argument | Type | Rule |
| --- | --- | --- |
| `query` | string | 1–500 characters (from the model) |
| `limit` | int | 1–10, default 5 (from the model) |
| `scope` | list of strings | Grounding items for this source: path prefixes or collection labels (added by the platform) |
| `max_class` | string | A data class id (added by the platform) |

Result (JSON text content):

```json
{"results": [{"source": "confluence", "document": "policies/ai-use.md",
  "section": "Controls > Human oversight", "title": "AI use policy",
  "snippet": "...", "content_hash": "sha256:...", "data_class": "internal",
  "synthetic": true}],
 "note": "3 results in scope"}
```

### `read`

| Argument | Type | Rule |
| --- | --- | --- |
| `document` | string | A document path from a search result (from the model) |
| `section` | string | Optional heading path; absent → the document outline (from the model) |
| `scope`, `max_class` | as above | Added by the platform |

Result: `{"source", "document", "section", "title", "text", "content_hash", "data_class",
"synthetic", "cut": bool}`. The text is at most 8,000 characters.

## Errors

These are returned as MCP tool errors with a plain message, which the agent receives:

- `out of scope`: the document is outside `scope`, or above `max_class`.
- `not found`: no such document or section.
- `invalid arguments`: for example, an empty query.

The server never returns documents with a missing or unknown data class.

## Platform side

The agents call the tools as `<source>_search` and `<source>_read`. `ToolGate` authorizes each call
with feature 004 (`mcp:<source>:read`) before `KnowledgeTool` adds `scope` and `max_class` from the
pinned spec. The model cannot set either.
