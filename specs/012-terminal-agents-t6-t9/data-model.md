# Data Model: Terminal Agents T6–T9 (feature 012)

- Migration `0010`: `tools.tool_result.kind` adds `observability`.
- Monitor evaluations: `run.policy_decision` rows, `check_id` = the monitor id, `run_id` = the
  use case's latest T8 run; a breach is a decision whose threshold evaluated true.
- Change decision: a new version of the ITSM `change` record: `status`, `decided_by`,
  `decided_at`, `comment`.
- Proposed event: a T8 `raised_events` row with `status: proposed`; its confirmation or dismissal
  is run activity on the T8 run (`step: event_confirmation`) and, when confirmed, the operational
  event itself.
- Platform-built artifacts (R-09): `T4.eval_baseline` `{metric, value, tolerance}` from the
  candidate's harness result; `T6.gate_evidence_summary` rows from run statuses, sign-offs and
  waivers. Agents cannot write them.
- Specs: agents catalogue 7.0.0; T6–T9 next major versions; prompts 1.0.0; playbooks 1.1.0.
