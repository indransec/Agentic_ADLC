---
id: PB-T9-01
version: "1.1.0"
title: T9 change impact
owner_role: adlc_coe
status: active
---
# T9 change impact

## Purpose

Decide how big a change is, from evidence, so it re-enters the lifecycle where it must be
revalidated, and no further back than needed.

## Procedure

1. Read the trigger evidence: the monitor, its threshold and the measured values; or the change
   request.
2. `agent_registry_read` and `cmdb_read`: the live version, its package and its dependants.
3. Write the artifacts.

## Steps per artifact

1. **change_impact_assessment** (`trigger, change_class, affected_components, risk_delta,
   reentry_terminal`): one row; `trigger` the event type; `affected_components` the components
   the evidence points at (a drop in answer quality with no change of ours points at the
   model: `model`); `change_class` from the terminal's change classes (model or tool:
   at least `moderate`; autonomy or data class: at least `major`); `reentry_terminal` the
   class's re-entry terminal.
2. **revalidation_plan** (`terminal, scope, owner, due`): one row per terminal on the class's
   path, with the scope (for example `delta`, `regression_only`) and the owner role.
3. **version_lifecycle_record** (`version, status, live_from, deprecated_on, sunset_on`): the live
   version (`live`) and, for a re-entry, the version that will replace it (`planned`).
4. **lessons_learned** (`lesson, source_terminal, playbook_update`): what the event teaches and
   which playbook should change (or `none`).
