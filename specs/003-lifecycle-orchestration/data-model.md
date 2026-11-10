# Data Model: Lifecycle Orchestration (003)

Migration `0003`. Names follow SA Annex A.6. Grants are listed per table. The app role
(`adlc_app`) is what the orchestrator and API use; the owner only migrates.

## Schema `run`

### `run.usecase`

| Column | Type | Rule |
| --- | --- | --- |
| `usecase_id` | text PK | `^UC-[0-9]{4}$`, from sequence `run.usecase_seq` |
| `name` | text | First line of the intake, max 200 characters |
| `intake_text` | text | Free text as submitted |
| `business_owner` | text | Account name of the submitter |
| `risk_tier` | text null | `low` \| `medium` \| `high`; set when T0 closes with emitted `risk_tier` |
| `status` | text | `active` \| `terminated` \| `closed` |
| `created_at`, `closed_at` | timestamptz | |

Grants for the app role: SELECT, INSERT, UPDATE (`risk_tier`, `status`, `closed_at` only;
enforced by a trigger).

### `run.terminal_run`

| Column | Type | Rule |
| --- | --- | --- |
| `run_id` | text PK | `<usecase_id>/T<n>/run-<k>` |
| `usecase_id` | text FK | |
| `terminal_id` | text | `^T[0-9]+$` |
| `run_number` | int | `k` ≥ 1; unique with (use case, terminal) |
| `spec_version` | text | Pinned version at open |
| `state` | text | One of the 9 states (contracts/state-machine.md) |
| `return_state` | text null | State to resume after a clarification |
| `mode` | text | `evolve` \| `retire` |
| `trigger_event_id` | uuid null | |
| `trigger_event_type` | text | |
| `trigger_context` | jsonb | Comment, root cause, causing run, ledger key, operational event payload |
| `rework_count` | int | Reworks routed to this terminal for this use case, including this run |
| `auto_retries` | int | Failed blocking-control retries in this run |
| `clarification_rounds` | int | |
| `artifacts` | jsonb | Latest artifacts (inline until 005's artifact store) |
| `control_results` | jsonb | Latest controls run |
| `recommendation` | jsonb null | Reviewer status, checklist scores, findings |
| `pending_waiver_id` | text null | |
| `escalation_trigger` | text null | `rework_limit` \| `timer` \| `clarification_limit` \| `clarification_sla` \| `retry_limit` \| `budget` |
| `final_status` | text null | `pass` \| `rework` \| `exception` \| `escalate` \| `terminate` |
| `version` | int | Optimistic concurrency, +1 per applied signal |
| `lease_until` | timestamptz null | Advancer lease |
| `opened_at`, `due_at`, `closed_at` | timestamptz | `due_at` = open + expected duration (tier) |

Constraints:

- A partial unique index on `(usecase_id, terminal_id) WHERE state <> 'closed'` gives one active
  run per use case and terminal (FR-003).
- A trigger refuses any update of a row whose state is `closed`.

Grants for the app role: SELECT, INSERT, UPDATE.

### Append-only `run` tables

Each of these has a trigger that refuses UPDATE and DELETE for every identity. App role: SELECT
and INSERT.

| Table | Columns |
| --- | --- |
| `run.run_transition` | `run_transition_id`, `run_id`, `from_state`, `to_state`, `signal_kind`, `actor_type` (`human` \| `agent` \| `reviewer` \| `orchestrator` \| `system`), `actor_id`, `reason`, `at` |
| `run.run_activity` | `run_activity_id`, `run_id`, `step` (`prerequisites` \| `build` \| `controls` \| `review` \| `clarification` \| `sign_off` \| `waiver` \| `escalation` \| `close` \| `route` \| `timer`), `actor_type`, `actor_id`, `started_at`, `ended_at`, `outcome`, `detail` jsonb |
| `run.sign_off` | `sign_off_id`, `run_id`, `role`, `person`, `decision`, `comment`, `root_cause`, `reason_differs`, `target_terminal`, `signed_at` |
| `run.clarification_round` | `clarification_id` (`<run_id>/clar-<k>`), `run_id`, `asked_by` (`agent` \| `reviewer`), `addressed_role`, `questions` jsonb, `looked_in` jsonb, `asked_at`; answered by one INSERT into `run.clarification_answer` (`clarification_id`, `answered_by`, `answers` jsonb, `answered_at`) |

### `run.waiver`

| Column | Type | Rule |
| --- | --- | --- |
| `waiver_id` | text PK | `^WVR-[0-9]{4}$` |
| `run_id` | text FK | |
| `waiver_owner`, `compensating_control` | text | |
| `expiry` | date | Must be after today |
| `recheck_at` | text[] | From the spec's exception outcome |
| `requires` | jsonb | Extra fields the spec requires (for example `risk_acceptance`) |
| `status` | text | `proposed` → `approved` \| `rejected`; `approved` → `expired` (by date, read-time) |
| `proposed_by`, `decided_by` | text | `decided_by` ≠ `proposed_by` |
| `proposed_at`, `decided_at` | timestamptz | |

Grants for the app role: SELECT, INSERT, UPDATE (`status`, `decided_*` only, while `proposed`;
enforced by a trigger).

### `run.timer`

`timer_id`, `run_id`, `kind` (`escalate_after` \| `clarification_sla` \| `review_due`),
`due_at`, `fired_at`, `cancelled_at`. App role: SELECT, INSERT, UPDATE.

## Schema `events`

### `events.outbox_event`

| Column | Type | Rule |
| --- | --- | --- |
| `event_id` | uuid PK | UUID v7 (time-ordered) |
| `event_type` | text | Annex A.3 |
| `usecase_id` | text null | Null only for events without a use case (none in the MVP) |
| `correlation_id` | text | `<usecase_id>/lifecycle` |
| `causation_run_id` | text null | |
| `payload` | jsonb | References only (contracts/events.md) |
| `created_at` | timestamptz | |
| `attempts` | int | |
| `next_attempt_at` | timestamptz | |
| `processed_at`, `dead_lettered_at` | timestamptz null | |
| `last_error` | text null | Truncated to 2,000 characters; no secrets (FR-015 of 001) |

Index `(usecase_id, created_at) WHERE processed_at IS NULL AND dead_lettered_at IS NULL`.

App role: SELECT, INSERT, UPDATE. A trigger allows updates only to the delivery columns
(`attempts`, `next_attempt_at`, `processed_at`, `dead_lettered_at`, `last_error`), so event
content is immutable.

### Other `events` tables

| Table | Columns | Grants for the app role |
| --- | --- | --- |
| `events.processed_event` | `event_id` PK, `processed_at` | SELECT, INSERT |
| `events.dead_letter_action` | `dead_letter_action_id`, `event_id`, `action` (`requeue`), `actor`, `at` | SELECT, INSERT (append-only) |
| `events.orchestrator_heartbeat` | `worker_id` PK, `beat_at` | SELECT, INSERT, UPDATE |

## Schema `ledger` (extends 001)

`ledger.ledger_record` gains `run_id text null`, `usecase_id text null` and
`content_json jsonb null`, plus a unique index on `run_id`. The append-only triggers stay. The
app role keeps SELECT and INSERT.

## Schema `spec` (from 002)

App role: INSERT on `spec.usecase_spec_pin` (pins written at submit).

## State and lifecycle rules

- **Run states and transitions**: [contracts/state-machine.md](contracts/state-machine.md).
- **Use case**: `active` → `terminated` (a terminate decision on any run) \| `closed` (the
  `lifecycle_closed` destination). No transition back.
- **Waiver**: `proposed` → `approved` \| `rejected`. An approved waiver reads as `expired` after
  its expiry date (checked by T6 and T8 controls in later features).
