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
| `attempt` | integer | |
| `item_id` | text | |
| `score` | integer null | |
| `finding` | text null | |
| `recorded_at` | timestamptz | |

### `run.terminal_run`

Adds `profile_version integer NOT NULL DEFAULT 0`: the profile version current when the run
opened.

### Views

| View | Rows |
| --- | --- |
| `run.v_run_step` | One per `run.run_activity` row: `run_id`, `step`, `actor_type`, `actor_id`, `started_at`, `ended_at`, `duration_seconds`, `outcome` |
| `run.v_usecase_terminal_summary` | Per `(usecase_id, terminal_id)`: `runs`, `reworks`, `clarification_rounds`, `escalations`, `automatic_seconds`, `waiting_seconds` (from transitions: the time spent in `opened`, `building`, `checking` and `reviewing`, versus `awaiting_clarification`, `awaiting_sign_off` and `escalated`) |

The app role gets SELECT on both views.
