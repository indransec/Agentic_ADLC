---
id: PB-T9-03
version: "1.1.0"
title: Retirement
owner_role: adlc_coe
status: active
---
# Retirement

## Purpose

Take an agent out of service so nothing can still act as it, its data is disposed of as its
retention requires, and no other agent is left depending on it without an owner.

## Procedure (retire mode only)

1. `agent_registry_read`: the agent and the agents that depend on it (`depends_on`); a dependant
   without an owner is a gap to report, not to fix.
2. `iam_revoke` the identity, then the tool scopes (two calls, `what` `identity` and
   `tool_scopes`), each with the reason.
3. `cmdb_write` the agent's configuration item with `data_status: disposed` once its memory, logs
   and data are disposed per T2's retention.
4. `agent_registry_write` the entry with `status: retired`.
5. `iam_read` to confirm the revocations.

## Steps per artifact

1. **retirement_record** (`step, completed_on, evidence_link`): one row per step of the terminal's
   retirement procedure, `evidence_link` the record id (`REV-<n>`, `CI-<n>`, `AG-<n>`).
2. **change_impact_assessment**: one row, `change_class` `strategic`, `reentry_terminal` `T0`
   (formal: the approvers close the lifecycle with their terminate decision, not a re-entry).
3. **closure_report**: never write it; the approvers' sign-off is the closure.
