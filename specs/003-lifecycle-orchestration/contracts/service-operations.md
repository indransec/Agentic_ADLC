# Contract: Orchestrator service operations

`OrchestratorService` (`orchestration/service.py`) is the only entry point for human and admin
actions. Feature 007 exposes it over HTTP. Every operation takes an `Actor` (a `Person` from
the 001 identity, or the system), runs in one transaction, and returns a result or raises a
typed error. Nothing is written on error.

| Operation | Who | Effect | Errors |
| --- | --- | --- | --- |
| `submit_usecase(actor, name, intake_text) -> usecase_id` | any signed-in person (becomes business owner) | Creates `UC-nnnn`; pins the active versions of all terminals; writes outbox `usecase.submitted` | `NoActiveSpecs` |
| `decide(actor, run_id, decision, *, comment, root_cause, reason, fields, target_terminal, expected_version)` | holder of an applicable sign-off role (R-12); terminate also limited by `set_by` | Applies signal `decide` | `NotAuthorised`, `InvalidDecision` (missing comment, root cause, reason or required fields; cause not routed; `not_allowed`; template not a re-entry), `StaleRun` (version moved), `InvalidTransition` |
| `decide_waiver(actor, waiver_id, approve: bool, comment)` | waiver approver role, not the proposer | Applies `waiver_decision` | `NotAuthorised`, `InvalidTransition` |
| `answer_clarification(actor, clarification_id, answers)` | holder of the addressed role | Applies `clarification_answered` | `NotAuthorised`, `AlreadyAnswered` |
| `complete_escalation(actor, run_id, artifacts)` | the terminal's A role | Applies `escalation_completed` | `NotAuthorised`, `InvalidTransition` |
| `raise_operational_event(actor, usecase_id, event_name, payload)` | system or agent identity with `raise_event` right (T8 status rights) | Writes outbox `T8.event.<name>` (terminal from the spec raising it) | `UnknownEvent` (not raised by any monitor of the pinned T8) |
| `list_dead_letters(actor) -> list[DeadLetter]` | `ADLC_DEADLETTER_ROLE` (default `adlc_coe`) | — | `NotAuthorised` |
| `requeue(actor, event_id)` | same | Resets delivery; writes `dead_letter_action` | `NotAuthorised`, `NotDeadLettered` |
| `get_run(run_id)`, `list_runs(usecase_id)`, `get_usecase(usecase_id)` | read-only; any signed-in person | — | — |

**Decision details** (`decision`: `pass` \| `rework` \| `exception` \| `terminate`):

- **rework** needs `comment` and `root_cause`. The cause must be in `route_by_root_cause`, or
  any root cause from the catalogue when the spec has a plain route. `owning_terminal`
  destinations need `target_terminal`.
- **exception** needs every field in the outcome's `requires`, as `fields`.
- **terminate** needs `reason` (passed as `comment`).
- **pass** must carry, in `fields`, every emitted value that is not an artifact (for example T0
  `risk_tier`, FR-018a). On a T9-style template route it takes the re-entry from the artifacts,
  or `alternative=<destination>` in `fields`.
- **pass** closes only when `min_approvers` distinct approvers have passed, plus every `plus`
  approver whose condition holds (FR-009b).
- **Any decision** that differs from the reviewer recommendation needs `reason`.
