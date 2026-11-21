# Data Model: End-to-End Demo on the Board (020)

No new platform table: change requests stay `enterprise_record` rows (feature 012); their board
items use 016's link table with `object_kind = 'change'`.

## Tracker mapping additions (`adlc-specs/tracker_mapping.yaml`)

```yaml
items:
  change:
    type: Change Request
    parent: run
    fields: {title: System.Title, description: System.Description, state: System.State,
             change_id: Custom.AdlcRunId}
    states: {awaiting: Awaiting approval, approved: Approved, rejected: Rejected}
decision:
  values: {…, approve_change: Approve change, reject_change: Reject change}
platform_written:
  change: [title, description, state, change_id]
```

## Simulator seed additions (`ado_sim/seed/demo.yaml`)

- Type `Change Request` (states Awaiting approval / Proposed, Approved / Completed, Rejected /
  Removed), the ADLC fields; a form section (Decision: decision, comment; Change: title, state,
  description).
- The decision field's allowed values gain Approve change and Reject change.

## Snapshot (`adlc.engagement.desired`)

- `ChangeSnapshot`: change_id, state (`new`, `approved`, `rejected`), summary, risk, window,
  decided_by. `RunSnapshot.changes: tuple[ChangeSnapshot, ...]`.

## Demo script additions (`demo/script.yaml`)

- Actions `board_change` {role, item: usecase|run, field: <mapping key>, value}, `drift` {item,
  field, value}, `reconcile` {}.
- Expectations `reverted: true`, `reconciled: true`.

## Settings

| Setting | Meaning |
| --- | --- |
| `ADLC_DEMO_BOARD_TOKENS` | the demo people's board tokens file (outside the repository; demo only) |
