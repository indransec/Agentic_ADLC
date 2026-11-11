# Data Model: Human Inbox

No new tables. The inbox and the run detail are read from the existing tables of features 003,
005 and 006 (research R-03, R-04). There is no migration.

## Derived views (in code)

### Inbox item

| Field | Rule |
| --- | --- |
| `kind` | `sign_off`, `clarification`, `escalation`, `waiver` or `dead_letter` |
| `id` | Run id, clarification id, waiver id or event id |
| `usecase_id`, `terminal_id`, `run_id` | From the run, or null for a dead letter |
| `role` | The person's role that makes the item theirs |
| `title` | Short text built by the platform (e.g. "Sign off T1 run 1"), never agent text |
| `arrived_at` | When the run entered the state, or the time asked or proposed |
| `due_at` | Run due time, or the clarification's SLA timer; null if none |
| `controls_pending` | Sign-off items only |

### Run detail `form`

| Field | Source |
| --- | --- |
| `outcomes` | `status_rights.human` of the pinned spec |
| `requires` | Per outcome, `outcome_model.<status>.requires` (e.g. waiver fields for exception) |
| `root_causes` | Keys of `outcome_model.rework.route_by_root_cause` |
| `typed_fields` | Emitted values a person must type (feature 003 `routing.emitted_values` missing) |
| `can_decide` | The person holds a still-needed sign-off role and has not approved |
| `can_edit` | The person holds a sign-off or accountable role, and the run is at sign-off or escalated |
| `reason_required_unless` | The reviewer's recommended status: a different decision needs a reason |

## Changes to existing interfaces (additive)

| Item | Change |
| --- | --- |
| `LedgerService.edit_artifact`, `upload_spreadsheet`, `attach_file` | Optional `expected_version`; a mismatch raises `StaleRun` |
| `OrchestratorService.complete_escalation` | Optional `expected_version` |
| `RuntimeSettings` | Gains `deadletter_role`, `synthetic_dir` and `spec_dir` (moved from `OrchestratorSettings`, same environment names) |
| `UiSettings` (new) | `api_url` (`ADLC_API_URL`) |
