# Contract: `adlc-specs/tracker_mapping.yaml`

Schema: `adlc-specs/schema/catalogues/tracker_mapping.schema.json`. Validated by `adlc-spec
validate` (rules V-32…V-36) and against the board by `adlc-board check-mapping` (R-12). Every
tracker name the platform uses comes from here (FR-003).

```yaml
catalogue: tracker_mapping
version: 1.0.0
inbound:
  mode: polling                  # only value in Option A
  poll_interval: 10s
area: "Agentic ADLC\\Use cases"
identities:
  match: board_identity          # account property compared with the board's unique name
items:
  usecase:
    type: Epic
    fields: {title: System.Title, description: System.Description, state: System.State,
             sub_stage: Custom.AdlcSubStage, usecase_id: Custom.AdlcUseCaseId,
             area: System.AreaPath}   # the Epic's area: registration reads it, creation sets it
    columns:                     # terminal id -> Epic state
      T0: "T0 Intake & Qualification"
      # ... one per terminal ...
    closed: Closed
    terminated: Removed
  run:
    type: Feature
    parent: usecase
    fields: {title: System.Title, description: System.Description, state: System.State,
             run_id: Custom.AdlcRunId, evidence: Custom.AdlcEvidenceLink}
    states:                      # run state -> item state
      opened: Active
      blocked: Active
      building: Active
      awaiting_clarification: Active
      checking: Active
      reviewing: Active
      awaiting_sign_off: Active
      escalated: Active
      closed: Closed
    terminated: Removed
  clarification:
    type: Task
    parent: run
    fields: {title: System.Title, description: System.Description, state: System.State,
             clarification_id: Custom.AdlcRunId, answer: Custom.AdlcClarificationAnswer}
    open: Active
    answered: Closed
sub_stages:                      # run state -> label written to the Epic's sub-stage
  opened: Opened
  blocked: Blocked
  building: Building
  awaiting_clarification: Awaiting clarification
  checking: Checking
  reviewing: Reviewing
  awaiting_sign_off: Awaiting sign-off
  escalated: Escalated
  closed: Closed
decision:
  field: Custom.AdlcDecision
  comment: Custom.AdlcComment
  values:                        # platform action -> value a person types or picks
    pass: Pass
    rework: Rework
    exception: Exception
    terminate: Terminate
    approve_waiver: Approve waiver
    reject_waiver: Reject waiver
    complete_escalation: Complete escalation
  inputs:                        # decision input -> field and comment label (FR-028)
    root_cause: {field: Custom.AdlcRootCause, label: root cause}
    reason: {field: Custom.AdlcReason, label: reason}
    target_terminal: {field: Custom.AdlcReworkTarget, label: rework target}
    values: {field: Custom.AdlcValues, label: value}   # comment form: "value <name>: <v>"
platform_written:                # a person's change to these is reverted (FR-017)
  usecase: [state, sub_stage, usecase_id]
  run: [title, description, state, run_id, evidence]
  clarification: [title, description, state, clarification_id]
```

## Rules

| Rule | Level | Checks |
| --- | --- | --- |
| V-32 | L2/L4 | the file matches its schema; `catalogue` is `tracker_mapping` |
| V-33 | L4 | every terminal in `terminals/` has a column; columns are distinct |
| V-34 | L4 | every run state of the state machine has an item state and a sub-stage |
| V-35 | L4 | every human outcome any terminal grants (`status_rights.human`), and the waiver and escalation actions, has a decision value; values are distinct |
| V-36 | L4 | every decision input has a field and a label; fields named in `platform_written` exist under that item |
| board check | runtime | every type, state and field exists in the board's process; the parent relation exists; the area exists; the service account authenticates |

Terminal ids appear only in this data file, never in code (constitution I; the scan of
`tests/unit/test_no_hardcoded_values.py` is extended to tracker names: types, states, fields and
decision values read from this file must not appear in `src/adlc`).
