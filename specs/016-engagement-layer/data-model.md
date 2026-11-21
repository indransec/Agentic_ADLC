# Data Model: Engagement Layer (016)

New tables in the platform's SQLite database (`ADLC_DB_PATH`), one Alembic migration
`db/migrations/versions/0002_board.py`. Times are the platform's `timestamptz` text (UTC). History
tables are append-only: triggers refuse `UPDATE` and `DELETE` for every connection, as for the
ledger (CLAUDE.md), and they join `APPEND_ONLY` checks in `scripts/migration_check`.

## Tables

**`board_link`**: one row per platform object shown on the board (FR-021).

| Column | Type | Notes |
| --- | --- | --- |
| object_kind | text | `usecase`, `run`, `clarification` |
| object_id | text | `UC-0001`, `UC-0001/T1/run-2`, `UC-0001/T1/run-2/clar-1` |
| work_item_id | integer | the board's id; unique |
| item_type | text | the mapped type it was created as |
| projected_hash | text | hash of the platform-written fields last written |
| last_written_rev | integer | the board revision the platform's last write produced |
| inbound_update_id | integer | the highest update id inbound sync has processed for this item |
| created_at, updated_at | timestamptz | |

PK (`object_kind`, `object_id`); unique (`work_item_id`). Mutable (it is current state, not
history).

**`board_sync_state`**: one row (`id = 1`).

| Column | Type | Notes |
| --- | --- | --- |
| watermark | text | the board's `asOf` of the last fully processed poll; null before the first |
| last_poll_at | timestamptz | |
| last_poll_outcome | text | `ok`, `board_unreachable`, `auth_failed`, `mapping_invalid` |
| last_error | text | ≤ 2,000 characters, no values or tokens |
| projection_cursor | JSON | high-water marks: `run_transition_id`, `run_activity_id`, `clarification_asked_at`, `clarification_answered_at`, `waiver_id`, `usecase_created_at` |

**`board_delivery`**: outbound state per use case (R-03).

| Column | Type | Notes |
| --- | --- | --- |
| usecase_id | text PK | FK `usecase` |
| dirty_since | timestamptz | null when delivered |
| attempts | integer | failures since the last success |
| next_attempt_at | timestamptz | from the outbox's `RETRY_DELAYS` |
| dead_lettered_at | timestamptz | set on the fifth failure; cleared by a requeue |
| last_error | text | ≤ 2,000 characters |
| delivered_at | timestamptz | last successful projection |

**`board_requeue`** (append-only): `id`, `usecase_id`, `actor`, `at`, the CoE's requeue of a
dead-lettered use case.

**`inbound_change`** (append-only): one row per board update read (FR-012, R-07).

| Column | Type | Notes |
| --- | --- | --- |
| work_item_id | integer | |
| update_id | integer | PK (`work_item_id`, `update_id`) |
| rev | integer | the item's revision after the update |
| changer | text | the board identity (unique name) |
| account_name | text | the mapped account, null if unmapped |
| kind | text | `own`, `baseline`, `register_usecase`, `decide`, `answer`, `revert_only`, `ignored` |
| object_id | text | the linked platform object, if any |
| read_at | timestamptz | |

**`inbound_outcome`** (append-only): written after the command.

| Column | Type | Notes |
| --- | --- | --- |
| work_item_id, update_id | | PK, FK `inbound_change` |
| outcome | text | `accepted`, `refused`, `ignored` |
| reason_code | text | `not_mapped`, `not_authorised`, `missing_input`, `invalid_input`, `stale`, `already_answered`, `unknown_value`, `closed`, `platform_field`, `invalid_usecase` |
| reason | text | the platform's message (≤ 2,000), never field values |
| command | text | `submit_usecase`, `decide:<status>`, `decide_waiver`, `complete_escalation`, `answer_clarification` |
| reverted | boolean | a revert was written to the board |
| at | timestamptz | |

**`board_reconciliation`** (append-only): `id`, `started_by`, `started_at`, `ended_at`,
`outcome` (`ok`, `failed`), `items_checked`, `differences` (JSON list of `{object_id,
work_item_id, field, board_value_hash, platform_value, action}`; board values are hashed, not
stored), `created_items`.

## Changes to existing data

- **Accounts file** (outside the repository): optional `board_identity` per account (string,
  unique, case-insensitive); `adlc.identity.accounts.FIELDS` gains it; existing files stay valid.
- **`run_activity.detail`**: commands applied from the board carry `"source": {"board_item": <id>,
  "update": <n>}` (R-06). No schema change (JSON).

## Board-neutral types (`engagement/model.py`)

| Type | Fields |
| --- | --- |
| `BoardItem` | `id`, `rev`, `type`, `state`, `fields` (reference → value), `parent_id`, `changed_by` |
| `BoardUpdate` | `item_id`, `update_id`, `rev`, `changed_by`, `changed_at`, `fields` (reference → (old, new)), `relations_added`, `relations_removed` |
| `ChangePage` | `item_ids`, `as_of` |
| `Identity` | `unique_name`, `display_name`, `id` |
| `ItemWrite` | `fields` to set, `fields` to clear, `parent_id`, `expected_rev` |

## Desired state (projector)

For a use case, `desired(usecase) -> list[DesiredItem]`, each `DesiredItem` = object kind and id,
item type, parent object, and the platform-written fields with their values (title, description,
state, sub-stage, ids, evidence link) plus `clear` (the person-input fields to empty, R-09). Its
hash is `projected_hash`. Pure: built from a snapshot of `usecase`, `terminal_run`,
`clarification_round`, `clarification_answer`, `waiver` and the run's decision form
(`inbox/forms.build_form` with a role-less system actor).

## State: one board change

```text
read ─► classified ─► claimed (inbound_change) ─► command applied ─► outcome (inbound_outcome)
                 │                                     │ refused
                 └─ own / ignored ─► outcome ignored   └─► revert written ─► outcome refused
```

## Validation rules

- `board_identity` unique across accounts; never equal to `ADLC_BOARD_SERVICE_IDENTITY`.
- A `work_item_id` links to one platform object; a platform object to one item.
- The watermark only moves forward and only to a board-issued `asOf`.
- An `(item, update)` pair has at most one `inbound_change` and one `inbound_outcome`.
