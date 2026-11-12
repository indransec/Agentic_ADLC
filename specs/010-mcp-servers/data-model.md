# Data Model: MCP Servers (feature 010)

## Platform database: schema `tools` (migration 0009)

All tables: SELECT and INSERT only for the app role (append-only, like the ledger).

### `tools.tool_call`

One row per tool call, including calls refused at the platform gate (FR-004).

| Column | Type | Rule |
| --- | --- | --- |
| `tool_call_id` | bigserial | key |
| `run_id`, `usecase_id`, `terminal_id` | text | from the run |
| `attempt`, `step` | int | agent attempt and step |
| `tool` | text | `<server>_<tool>` |
| `server`, `scope` | text | from the binding |
| `arguments_sha256` | text | `sha256:` of the canonical JSON of the arguments sent (never the arguments) |
| `outcome` | text | `ok`, `refused`, `failed`, `timed_out`, `unavailable` |
| `reason` | text | for every outcome other than `ok` |
| `duration_ms` | int | |
| `at` | timestamptz | |

### `tools.tool_result`

The full answer of an evidence tool (research R-04), written by the platform.

| Column | Type | Rule |
| --- | --- | --- |
| `tool_result_id` | bigserial | key |
| `tool_call_id` | bigint | references `tool_call` |
| `run_id`, `usecase_id`, `terminal_id` | text | |
| `kind` | text | `ci`, `harness`, `redteam`, `dlp`, `deploy`, `traffic`, `kill_switch`, `environment` |
| `package_hash` | text | when the result is about a package |
| `result` | jsonb | the server's answer (no incident text) |
| `result_sha256` | text | `sha256:` of the canonical JSON |
| `at` | timestamptz | |

### `tools.enterprise_record`

The mocks' records. A change is a new version; the highest version is current.

| Column | Type | Rule |
| --- | --- | --- |
| `enterprise_record_id` | bigserial | key |
| `system` | text | `servicenow`, `cmdb`, `agent_registry`, `iam`, `grc`, `eval_store` |
| `kind` | text | `change`, `incident`, `ci`, `agent`, `revocation`, `report`, `note` |
| `record_id` | text | `CHG-<n>`, `INC-<n>`, `CI-<n>`, `AG-<n>`, `REV-<n>`, `GRC-<n>`, `NOTE-<n>` |
| `version` | int | 1, 2, … per `record_id` |
| `usecase_id`, `run_id`, `terminal_id` | text | from the token |
| `body` | jsonb | the record's fields |
| `at` | timestamptz | |

Unique (`system`, `record_id`, `version`).

## Bridge volume `bridge-data`

| Path | Holds |
| --- | --- |
| `git/<usecase_id>.git` | Bare repository per use case; `main` has the empty fill layout |
| `records/calls.jsonl` | The bridge's own audit: time, run, tool, outcome (no arguments) |
| `records/pull_requests.jsonl` | `{at, usecase_id, run_id, branch, commit, title, pull_request}` |
| `records/monitors.jsonl` | Monitor definitions and fired events (append-only; latest definition wins) |
| `prompts/<sha256>.txt` | Prompt registry texts |
| `artifacts/<sha256>.txt` | Build notes |

## Spec catalogue changes

| File | Change | Version |
| --- | --- | --- |
| `adlc-specs/shared/mcp_servers.yaml` | Every entry gains `host` (`knowledge`, `tools`, `bridge`); new `pilot_env` (`dev`, `test`, `read`); `cd` adds `read` | 2.0.0 |
| `adlc-specs/schema/catalogues/mcp_servers.schema.json` | `host` required, enum | — |
| `adlc-specs/terminals/T3.yaml` | Tool scopes add `mcp:pilot_env:dev`, `mcp:pilot_env:read`, `mcp:git:read`, `mcp:artifact_store:read` | 2.0.0 |
| `adlc-specs/terminals/T4.yaml` | Add `mcp:pilot_env:test`, `mcp:pilot_env:read`, `mcp:artifact_store:read` | 2.0.0 |
| `adlc-specs/terminals/T5.yaml` | Add `mcp:pilot_env:test`, `mcp:pilot_env:read` | 2.0.0 |

## Platform data files

| File | Holds |
| --- | --- |
| `data/redteam/suite.yaml` | Versioned attacks: id, category, payload, check (`marker_in_answer`, `field_equals`, `planted_pii_in_answer`, `toxic_in_answer`) with its parameters |
| `data/controls/controls.yaml` | Control library: id, title, topic, description |

## Pilot data file

`pilot/datasets.yaml`: `{id, version, seed, size, pii_share, scored_fields: [team, category,
priority], slices: [{name, field, value}]}`. Defaults: `golden` (seed 7, 200), `regression` (seed
2026, 500), `pii` (seed 5, 100, PII share 1.0).

## Evidence sources (research R-12)

| Source | Value |
| --- | --- |
| `env.dev`, `env.test` | `{provisioned, healthy, deployed_hash, infra_version}`; `provisioned` = the host answers and its definition loads |
| `env.prod` | `{deployed_hash}`: prod-sim's stable hash (a full rollout promotes the candidate to stable) |
| `template.version` | The template version from the infrastructure resources (e.g. `incident-triage@1.0.0`) |
