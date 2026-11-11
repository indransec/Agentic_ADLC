# Data Model: Terminal Agents T0–T2

## New tables (migration 0008, schema `run`)

Both tables are append-only for every database identity: the immutability trigger of features
003 and 005 refuses UPDATE and DELETE.

### `run.knowledge_retrieval`

One row per knowledge result returned to an agent (FR-021, research R-04).

| Column | Type | Rule |
| --- | --- | --- |
| `knowledge_retrieval_id` | bigint identity | Primary key |
| `run_id` | text | References `run.terminal_run` |
| `attempt` | int | The agent attempt (feature 006) |
| `step` | int | The model step that asked for it |
| `source` | text | A catalogue MCP server id, e.g. `confluence` |
| `operation` | text | `search` or `read` |
| `request` | text | The query or the document asked for, at most 500 characters |
| `document` | text | Path within the source, e.g. `policies/ai-use.md` |
| `section` | text | Section heading path, `''` for the whole document |
| `content_hash` | text | `sha256:<hex>` of the section text returned |
| `data_class` | text | The document's class |
| `synthetic` | boolean | From the document's front matter |
| `retrieved_at` | timestamptz | |

Index: `(run_id, attempt)`.

### `run.artifact_citation`

One row per citation an agent gave, linked to the artifact version it supports (FR-015, FR-016).

| Column | Type | Rule |
| --- | --- | --- |
| `artifact_citation_id` | bigint identity | Primary key |
| `run_id` | text | |
| `artifact_id` | text | An artifact of the run's terminal |
| `version` | int | The artifact version created by the same attempt; references `run.artifact_version` |
| `row_index` | int, null | Index of the supported row; null for the whole artifact |
| `source`, `document`, `section` | text | As retrieved |
| `content_hash` | text | Copied from the matching retrieval, never from the model |
| `knowledge_retrieval_id` | bigint | References the matching retrieval |
| `cited_at` | timestamptz | |

Index: `(run_id, artifact_id, version)`.

## Changed records and catalogues

| Item | Change |
| --- | --- |
| `adlc-specs/shared/agents.yaml` | 1.1.0. T0–T2 agents become `implementation: model`, `version: 1.1.0`, with `prompt` and `tools` (`<source>_search` and `<source>_read`, permission `mcp:<source>:read`) for the sources in both `tool_scopes` and the grounding entries |
| `adlc-specs/prompts/t0-intake-agent.md`, `t1-requirements-agent.md`, `t2-architect-agent.md` | New, version 1.0.0 |
| Nine playbooks (T0–T2) | 1.1.0, `status: active`, real procedures |
| `adlc-specs/terminals/T0.yaml`, `T1.yaml`, `T2.yaml` | 1.1.0. The playbook references move to 1.1.0; nothing else changes |
| Builder output (feature 006) | Optional `citations: [{artifact, row?, source, document, section}]` beside `artifacts` |
| Agent attempt (feature 006) | Unchanged columns; retrievals and citations link by run and attempt |
| Run detail (feature 007) | `citations` per artifact |

## Files

### Knowledge document (`<ADLC_KNOWLEDGE_DIR>/<source>/<path>.md`)

```yaml
---
title: AI use policy
data_class: internal          # an id from data_classes.yaml; missing or unknown → not served
synthetic: true
collections: [policies]       # labels matched by grounding scopes that are not paths
version: "1.0.0"
---
# AI use policy
## Scope
...
```

Sections are the Markdown headings. A section's id is its heading path (`Scope`,
`Controls > Human oversight`).

### Reference use case (`data/reference_usecases/<id>.yaml`)

| Field | Meaning |
| --- | --- |
| `id`, `name` | e.g. `travel-claims`, "Travel Claims Assistant" |
| `intake_text` | The business owner's description (at least 200 characters) |
| `answers` | Prepared clarification answers by addressed role, given in order |
| `approver_fields` | Values typed at pass, by terminal (e.g. T0 `risk_tier`) |
| `expected` | Expected risk tier and minimum checks for the report |

### Recording (`<dir>/<usecase>/<agent>.jsonl`)

One model reply per line, in call order. The reviewer has its own file. Replies are stored as
returned (content and usage). There are no prompts and no keys.

### Replay report (`reports/replays/<timestamp>/report.json` and `report.md`)

Per use case and terminal:
- mandatory artifacts present and missing;
- blocking controls passed and failed;
- reviewer recommendation, reason and root cause;
- clarifications asked;
- citations given;
- steps, tokens and cost;
- agent, prompt and playbook versions and hashes, and model and provider.

With a baseline, each row also says whether the recommendation changed.

## Validation rules

- **Citations:** each citation matches a retrieval of the same attempt (source, document, section);
  otherwise output validation fails (FR-016).
- **Addressee:** a clarification's `addressed_role` is empty or one of the terminal's human roles
  (clarification answer 3).
- **Server-side filtering:** the knowledge server returns only documents in the request's scope
  and at or below its maximum class. A document with no valid class is never returned.
