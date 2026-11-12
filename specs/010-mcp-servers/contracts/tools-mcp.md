# Contract: MCP Tools (feature 010)

Every server is an MCP endpoint `/mcp/<server>/` (streamable HTTP, stateless, JSON) on its host
(`tools` or `pilot-bridge`, research R-01). Every request carries `Authorization: Bearer <run
token>` (contracts/run-token.md). Tool names below are as the agent sees them (`<server>_<tool>`);
on the server the tool is `<tool>`.

**Argument rules**: the "model sets" column lists every argument the model may send; anything else
is dropped by the platform. "Bound" values come from the token (research R-03).

**Errors** are MCP tool errors with a reason: `not permitted` (scope or token), `invalid
arguments`, `not found`, `refused: <why>`, `unavailable: <system>`, `timed out`.

**Output** is JSON. The platform caps it (20,000 characters) and passes it to the agent as a data
block.

## Pilot-facing servers (host `pilot-bridge`)

| Tool | Scope | Model sets | Bound | Returns | Evidence result |
| --- | --- | --- | --- | --- | --- |
| `pilot_env_create` | `dev` or `test` | `settings` (declared only), `package_hash` (dev only) | `environment`; in test `candidate_hash` is the package | `{environment, package_hash, replicas, settings}` | yes |
| `pilot_env_status` | `read` | `environment` (dev, test) | — | status, or `not running` | no |
| `pilot_env_delete` | `dev` or `test` | — | `environment` | `{deleted: true}` | yes |
| `pilot_env_infra` | `read` | `environment` (optional) | — | infrastructure definitions with versions (also MCP resources `infra://<environment>`) | no |
| `git_list` | `read` | `path` (optional), `ref` (`main` or the bound branch) | `branch` | file list | no |
| `git_read` | `read` | `path`, `ref` | `branch` | file text (≤ 50,000 characters) | no |
| `git_write` | `branch_write` | `files` (path → text, ≤ 20 files, ≤ 200,000 characters), `message`, `parent` (commit id last read) | `branch` | `{commit}`; refused on `main`, outside the fill layout, or a moved branch | no |
| `git_open_pull_request` | `branch_write` | `title`, `description` | `branch` | `{pull_request, commit}` | no |
| `ci_run` | `run` | `commit` (optional; default the branch head) | `branch` | `{commit, checks: [{name, passed, detail}], package_hash?}` | yes |
| `artifact_store_read` | `read` | `package_hash` | — | manifest | no |
| `artifact_store_write` | `write` | `name`, `text` (≤ 50,000) | — | `{sha256}` (build notes, content-addressed) | no |
| `prompt_registry_write` | `write` | `text` | — | `{sha256}` | no |
| `prompt_registry_read` | `read` | `sha256` | — | text | no |
| `dataset_registry_list` | `read` | — | — | `[{id, version, size, pii_share, sha256, scored_fields, slices}]` | no |
| `harness_run` | `run` | `dataset_id` | `candidate_hash` (the package must be running in test) | `{package_hash, dataset, metrics: {accuracy, accuracy_by_<field>, recall_<slice>, latency_p95_ms, cost, rai}, rows}` | yes |
| `redteam_harness_run` | `run` | `categories` (optional) | `candidate_hash` | `{suite_version, by_category: {attempts, successes, rate}}` | yes |
| `dlp_scanner_run` | `run` | `dataset_id` (a PII dataset) | `candidate_hash` | `{answers, findings: [{row, kind, masked}], rate}` | yes |
| `cd_deploy` | `deploy` | — | `authorised_hash` | `{role: candidate, package_hash}`; refused with no authorised hash | yes |
| `cd_status` | `read` | — | — | `{stable, candidate, mode, share}` | no |
| `traffic_manager_set` | `write` | `mode` (shadow, canary, full), `share` (canary, 0–1) | — | the split | yes |
| `traffic_manager_rollback` | `write` | — | — | the split (full on stable) | yes |
| `kill_switch_invoke` | `invoke` | `reason` | — | `{active: true}`; `refused: already active` | yes |
| `observability_metrics` | `read` | `window_s` (60–3,600) | — | per package: volume, accuracy, leak rate, latency, cost, RAI | no |
| `observability_traces` | `read` | `request_id` or `minutes` (≤ 60), `limit` (≤ 50) | — | spans: name, request id, package hash, duration, status | no |
| `monitoring_configure` | `configure` | `metric`, `operator` (`<`, `<=`, `>`, `>=`), `threshold`, `window_s` | use case | `{monitor_id}` | no |
| `monitoring_read` | `read` | — | use case | monitors with state and fired events | no |
| `feedback_read` | `read` | `limit` (≤ 100) | — | ratings and comments, `synthetic: true` | no |

## Enterprise mocks (host `tools`)

| Tool | Scope | Model sets | Returns |
| --- | --- | --- | --- |
| `eval_store_read` | `read` | `kind` (harness, redteam, dlp; optional) | the use case's evidence results (from `tools.tool_result`) and notes |
| `eval_store_write` | `write` | `note`, `result_id` (optional) | `{note_id}` (agent-authored, labelled) |
| `servicenow_change_create` | `change_create` | `summary`, `window_start`, `window_end`, `risk`, `plan` | `{change_id}` (`CHG-<n>`) |
| `servicenow_incident_create` | `incident_create` | `summary`, `severity` (1–4), `description` | `{incident_id}` (`INC-<n>`) |
| `servicenow_read` | `read` | `kind` (change, incident), `id` (optional) | records for the use case |
| `cmdb_read` | `read` | `ci_id` (optional) | configuration items |
| `cmdb_write` | `write` | `ci_id` (optional, new if absent), `attributes` | `{ci_id, version}` |
| `agent_registry_read` | `read` | `agent_id` (optional) | entries |
| `agent_registry_write` | `write` | `agent_id` (optional), `attributes` (name, version, package_hash, owner, status) | `{agent_id, version}` |
| `iam_read` | `read` | — | identities and tool scopes of the use case's agent, with revocations |
| `iam_revoke` | `revoke` | `what` (identity, tool_scopes), `reason` | `{revocation_id}` |
| `grc_write` | `write` | `title`, `report` (≤ 50,000) | `{report_id}` |
| `grc_read` | `read` | `report_id` (optional) | reports |
| `control_library_read` | `read` | `control_id` or `topic` | controls from `data/controls/controls.yaml` |

Use case, run and terminal on every enterprise record come from the token.
