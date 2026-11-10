# Data Model: Policy Engine (004)

Migration `0004`. Both tables are append-only for every identity (triggers raise SQLSTATE
42501, as in 003). The app role gets SELECT and INSERT.

## `run.policy_decision`

| Column | Type | Rule |
| --- | --- | --- |
| `policy_decision_id` | bigint identity PK | |
| `kind` | text | `evaluate` \| `authorize` |
| `run_id` | text null | The run the decision is for (null only for a request with no run, which is always refused) |
| `usecase_id` | text null | |
| `terminal_id` | text null | |
| `check_id` | text | Prerequisite or control id, `plus:<role>`, `external:<body>`, `then_when:<event>`, or `authorize` |
| `rule` | text | The expression, or `<action>:<resource>` for authorize |
| `actor` | text null | For authorize |
| `passed` | boolean | |
| `value` | jsonb null | The computed value (CEL result converted to JSON) |
| `reason` | text | Always set; up to 2,000 characters |
| `inputs` | jsonb | Scalars in full; tables as `{ref, rows, content_hash}`; each with `source` and `synthetic` |
| `synthetic` | boolean | True when any input came from the synthetic provider (FR-025) |
| `fail_safe` | boolean | True when the result was decided by the fail-safe rule (R-09) |
| `duration_ms` | numeric | |
| `decided_at` | timestamptz | |

Index: `(run_id, decided_at, policy_decision_id)`.

## `run.run_parameter_set`

| Column | Type | Rule |
| --- | --- | --- |
| `run_id` | text PK, FK `run.terminal_run` | One set per run, frozen (FR-014) |
| `risk_tier` | text | The tier used (`medium` when the use case has none yet) |
| `guardrail_version` | text | Catalogue version of `guardrails` |
| `parameters` | jsonb | `{name: {value, source: usecase \| guardrail, unit, direction}}` |
| `rejected` | jsonb | `[{name, proposed, tier_value, reason}]` for use-case values not used (FR-013) |
| `resolved_at` | timestamptz | |

## Changes to feature 003 data

- **Control results**: each entry in `run.terminal_run.control_results` gains
  `synthetic: bool`. It is a jsonb field, so no migration is needed.
- **Actor ids**: agent and reviewer signals use `agent:<run_id>` and `reviewer:<run_id>`
  (R-07). The `run.run_transition.actor_id` column is text, so no migration is needed.

## Non-database data

| File | Content |
| --- | --- |
| `data/synthetic/evidence.yaml` | Per source (`env`, `ci`, `sbom`, `redteam`, `dlp`, `telemetry`, `change`, `template`, `dataset`, `release`, `portfolio`, `retirement`, `directory`), the field values defined in `evidence_sources.yaml` |
| `data/synthetic/artifacts/T<n>.yaml` | `{<artifact id>: [rows]}` meeting the terminal's blocking controls, with hashes consistent with `evidence.yaml` |

## Pure value objects

| Object | Fields |
| --- | --- |
| `EvalResult` (003, extended) | `passed`, `value`, `reason`, `synthetic` (default false) |
| `Evidence` | `value`, `source`, `synthetic` |
| `NOT_AVAILABLE` | Sentinel for a source with no provider |
| `ResolvedParameters` | `values: {name: value}`, `sources`, `rejected`, `tier` |
