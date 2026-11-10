# Data Model: Evidence Ledger (005)

Migration `0005`. Every new table is append-only for every identity (triggers raise SQLSTATE
42501, reusing `run.reject_mutation()`). The app role gets SELECT and INSERT unless stated
otherwise.

## Schema `ledger`

### `ledger.content_blob` (structured content)

| Column | Type | Rule |
| --- | --- | --- |
| `content_hash` | text PK | `^sha256:[0-9a-f]{64}$`; SHA-256 of the normal form of `body` |
| `body` | jsonb | |
| `size` | integer | Bytes of the normal form |
| `stored_at` | timestamptz | |

### `ledger.file_object` (files in the file store)

| Column | Type | Rule |
| --- | --- | --- |
| `content_hash` | text PK | SHA-256 of the bytes |
| `size` | bigint | ≤ `ADLC_ATTACHMENT_MAX` |
| `media_type` | text | On the allow list |
| `stored_at` | timestamptz | |

### `ledger.profile_version`

| Column | Type | Rule |
| --- | --- | --- |
| `usecase_id` | text FK `run.usecase` | |
| `version` | integer | ≥ 1; PK with `usecase_id` |
| `profile_values` | jsonb | Merged values; artifact references as `{artifact, version, content_hash}` |
| `source_run_id` | text FK `run.terminal_run` | |
| `created_at` | timestamptz | |

### `ledger.verification_run`

| Column | Type | Rule |
| --- | --- | --- |
| `verification_run_id` | bigint identity PK | |
| `actor` | text | Account name, or `cli:<os user>` |
| `scope` | text | `UC-nnnn` or `all` |
| `started_at`, `finished_at` | timestamptz | |
| `records_checked` | integer | |
| `breaks` | jsonb | List of `{ledger_key, check, element, expected, actual}` |
| `verified` | boolean | True when there are no breaks |

### `ledger.ledger_record` (unchanged table)

New records carry `content_json.content_version = 2` (contracts/record.md). The columns are
unchanged.

## Schema `run`

### `run.artifact_version`

| Column | Type | Rule |
| --- | --- | --- |
| `run_id` | text FK `run.terminal_run` | |
| `artifact_id` | text | An artifact id of the pinned spec |
| `version` | integer | ≥ 1; PK `(run_id, artifact_id, version)` |
| `content_hash` | text FK `ledger.content_blob` | |
| `producer_type` | text | `agent` \| `person` |
| `producer_id` | text | `agent:<run_id>` or the account name |
| `attempt` | integer null | The build attempt, for agent versions |
| `derived_from_version` | integer null | |
| `schema_valid` | boolean | |
| `created_at` | timestamptz | |

### `run.artifact_attachment`

| Column | Type | Rule |
| --- | --- | --- |
| `run_id`, `artifact_id`, `version` | | FK to `run.artifact_version` |
| `content_hash` | text FK `ledger.file_object` | PK with the three above |
| `file_name` | text | 1–255 characters, no path separators |
| `media_type`, `size` | | Copied from `file_object` |

### `run.checklist_result`

| Column | Type | Rule |
| --- | --- | --- |
| `checklist_result_id` | bigint identity PK | |
| `run_id` | text FK | |
| `attempt` | integer | `auto_retries + 1` when the review completed |
| `item_id` | text | |
| `score` | integer null | |
| `finding` | text null | |
| `recorded_at` | timestamptz | |

### `run.terminal_run`

Adds three columns:

| Column | Type | Rule |
| --- | --- | --- |
| `profile_version` | integer NOT NULL DEFAULT 0 | The profile version current when the run opened |
| `approvals_after_sign_off_id` | bigint null | Set by an artifact edit to the highest `run.sign_off` id at that time; pass approvals at or below it no longer count (FR-010) |
| `controls_pending` | boolean NOT NULL DEFAULT false | Set by an edit while awaiting sign-off; cleared when the worker re-runs the controls. While set, `pass` and `exception` are refused, and the worker leases the run to re-check it, including after a crash (FR-010) |

### `run.policy_decision` (feature 004)

Adds `attempt integer NULL`: the build attempt (`auto_retries + 1`) a control decision checked.
It is null for prerequisites and conditions. A second evaluation within one attempt is a
re-check after an edit (FR-020).

### Signals (feature 003 state machine)

| Signal | Actor | Effect |
| --- | --- | --- |
| `artifact_edited` | human | StoreArtifacts (person version); ClearApprovals; WithdrawWaiver when one is pending; SetControlsPending(true) at sign-off. The state does not change. |
| `controls_rechecked` | orchestrator | StoreControls; SetControlsPending(false). The state does not change. |

### Views

| View | Rows |
| --- | --- |
| `run.v_run_step` | One per `run.run_activity` row: `run_id`, `step`, `actor_type`, `actor_id`, `started_at`, `ended_at`, `duration_seconds`, `outcome` |
| `run.v_usecase_terminal_summary` | Per `(usecase_id, terminal_id)`: `runs`, `reworks`, `clarification_rounds`, `escalations`, `automatic_seconds`, `waiting_seconds` (from transitions: the time spent in `opened`, `building`, `checking` and `reviewing`, versus `awaiting_clarification`, `awaiting_sign_off` and `escalated`) |

The app role gets SELECT on both views.
