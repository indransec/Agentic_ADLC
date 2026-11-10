# Data Model: Agent Runtime

Migration `0006_agent_runtime`.

The new tables are append-only for every identity. They reuse `run.reject_mutation()` for
UPDATE, DELETE and TRUNCATE. The app role gets SELECT and INSERT; the views get SELECT.

## `spec.prompt_registry` (spec schema, written by `adlc-spec register`)

| Column | Type | Rule |
| --- | --- | --- |
| `prompt_registry_id` | bigint identity PK | |
| `prompt_id` | text | `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` (the agent id it serves, e.g. `common-terminal-reviewer`) |
| `version` | text | semantic version |
| `path` | text | `prompts/<file>.md` |
| `content_hash` | text | `sha256:` and 64 hex characters, over the normalised body |
| `registered_at` | timestamptz | default now() |
| | | UNIQUE (`prompt_id`, `version`); a changed body needs a new version (the playbook rule) |

## `run.agent_attempt`

One row per build or review attempt, written when the attempt ends.

| Column | Type | Rule |
| --- | --- | --- |
| `agent_attempt_id` | bigint identity PK | |
| `run_id` | text FK `run.terminal_run` | |
| `kind` | text | `build` or `review` |
| `attempt` | integer ≥ 1 | build: `auto_retries + 1`; review: the run's review count + 1 |
| `agent_id`, `agent_version` | text | from the agents catalogue |
| `implementation` | text | `stub` or `model` |
| `prompt_hash` | text null | null for stubs |
| `playbook_hashes` | jsonb | `{playbook_id: hash}` |
| `context_hash` | text | `sha256:…` of the context pack |
| `steps`, `tokens_in`, `tokens_out` | integer | totals for the attempt |
| `cost_usd` | numeric(14,6) null | null when any call's price is unknown |
| `corrections` | integer | corrections used |
| `outcome` | text | `artifacts`, `clarification`, `recommendation`, `budget_exceeded`, `failed`, `model_unavailable` |
| `limit_reached` | text null | `steps`, `tokens` or `timeout` |
| `reason` | text null | at most 2,000 characters; never artifact content |
| `started_at`, `ended_at` | timestamptz | |

## `run.model_call`

One row per request to a provider, including the ones that failed.

| Column | Type | Rule |
| --- | --- | --- |
| `model_call_id` | bigint identity PK | |
| `agent_attempt_ref` | text | `run_id/kind/attempt`, joined when the attempt row is written |
| `run_id`, `usecase_id`, `terminal_id` | text | |
| `agent_id` | text | |
| `tier` | text | a model tier id |
| `entry_index` | integer | the position in the tier list (1 is the primary) |
| `provider`, `model` | text | e.g. `anthropic`, `anthropic/claude-opus-5-5` |
| `prompt_hash`, `context_hash` | text | |
| `tokens_in`, `tokens_out` | integer | |
| `usage_estimated` | boolean | true when the provider sent no usage figures |
| `cost_usd` | numeric(14,6) null | null when the price is unknown |
| `cost_known` | boolean | |
| `latency_ms` | numeric | |
| `outcome` | text | `ok`, `outage`, `refusal`, `truncated`, `request_error`, `skipped` |
| `reason` | text null | e.g. `rate_limit`, `timeout`, `no_key`, `data_class`, `auth` |
| `fallback` | boolean | true when this answer did not come from the first runnable entry |
| `tried` | jsonb NOT NULL DEFAULT '[]' | the entries tried before this one, each `{model, outcome, reason}` (FR-007) |
| `called_at` | timestamptz | |

## `run.cost_alert`

| Column | Type | Rule |
| --- | --- | --- |
| `cost_alert_id` | bigint identity PK | |
| `usecase_id` | text | |
| `level_usd` | numeric(14,2) | |
| `total_usd` | numeric(14,6) | the total when the level was reached |
| `recorded_at` | timestamptz | |
| | | UNIQUE (`usecase_id`, `level_usd`) |

## Changes to existing tables

| Table | Change |
| --- | --- |
| `run.terminal_run` | `model_unavailable_since timestamptz NULL`: set by the first outage deferral, cleared by any other step result |
| `run.terminal_run` | The escalation-trigger check adds `model_unavailable` and `reviewer_failed` |

## Views

| View | Gives |
| --- | --- |
| `run.v_run_cost` | Per run: calls, tokens in and out, known cost, unknown-cost calls, fallback answers |
| `run.v_terminal_cost` | Per use case and terminal: the same totals |
| `run.v_usecase_cost` | Per use case: the same totals |

## Catalogues (in `adlc-specs/shared/`)

**`model_catalogue.yaml`**: `catalogue: model_catalogue`, then
`profiles: {<profile>: {<tier>: [entry, ...]}}`. A `default` profile is required, and every
profile covers every tier. Each entry has:

- `provider`: `anthropic`, `openai` or `gemini`;
- `model`: the LiteLLM id;
- `input_per_mtok` and `output_per_mtok`: USD, or null for unknown;
- `max_output_tokens` and `context_tokens`: the model's limits (the gateway caps `max_tokens`,
  and skips the entry when the context does not fit);
- `max_data_class`: a data class id;
- `params`: optional, a map passed to the provider.

**`agents.yaml`**: `catalogue: agents`, then `agents: [entry, ...]`. Each entry has:

- `id` and `version`;
- `prompt: {id, version}`, required when `implementation` is `model`;
- `model_tier`;
- `tools`: permission patterns;
- `implementation`: `stub` or `model`.

## Feature 003 interfaces (additions only)

| Item | Addition |
| --- | --- |
| `AgentResult`, `ReviewResult` | New union members `AttemptFailed(reason)` and `ModelUnavailable(detail)` |
| `Recommendation` | Optional `reason: str = ""`, `root_cause: str | None = None`, `reviewer: str = "stub"` |
| `BudgetExceeded` | `detail` names the limit (`tokens`, `steps` or `timeout`) |

## States

There are no new run states. The transitions added to feature 003's state-machine contract are
in [contracts/state-machine-additions.md](contracts/state-machine-additions.md).
