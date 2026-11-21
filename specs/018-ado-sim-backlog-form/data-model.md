# Data Model: ADO Simulator Backlog and Work Item Form (018)

No new table. Seed additions (data, validated), stored as JSON in `board_setting`:

```yaml
process:
  types:
    Epic:
      fields: &adlc_fields
        - {ref: Custom.AdlcDecision, allowed_values: [Pass, Rework, Exception, Terminate,
           Approve waiver, Reject waiver, Complete escalation]}
        # ... the other ADLC fields unchanged ...
form:
  Epic:
    - {title: Use case, fields: [System.Title, System.State, Custom.AdlcSubStage, Custom.AdlcUseCaseId, System.AreaPath, System.Description]}
  Feature:
    - {title: Decision, fields: [Custom.AdlcDecision, Custom.AdlcComment, Custom.AdlcRootCause, Custom.AdlcReason, Custom.AdlcReworkTarget, Custom.AdlcValues]}
    - {title: Run, fields: [System.Title, System.State, Custom.AdlcRunId, Custom.AdlcEvidenceLink, System.Description]}
  Task:
    - {title: Clarification, fields: [System.Description, Custom.AdlcClarificationAnswer]}
    - {title: Details, fields: [System.Title, System.State, Custom.AdlcRunId]}
```

Validation: every type and field exists (the field on that type); a field at most once per type.

## View models

- **FormField**: reference, label, kind (`select`, `text`, `textarea`, `number`, `datetime`,
  `identity`, `checkbox`, `readonly`), value (as text), choices, error.
- **Section**: title, fields.
- **HistoryEntry**: who, when, changes (label, old, new, shortened flags), link changes.
- **TreeRow**: id, type, title, state, depth, children, open.
