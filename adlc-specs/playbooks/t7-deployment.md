---
id: PB-T7-01
version: "1.1.0"
title: T7 deployment
owner_role: adlc_coe
status: active
---
# T7 deployment

## Purpose

Put exactly the package that was built, tested and assured into production, in stages, with
measured evidence for every stage and an immediate rollback on a breach; then hand it over to
operations.

## Procedure

1. `cd_status`, then `cd_deploy` (the platform supplies T6's authorised package; it becomes the
   candidate in prod-sim).
2. For each stage of T6's `rollout_plan`, in order: `traffic_manager_set` (`mode` is the stage;
   for `canary`, `share` is the plan's traffic percentage / 100), then `observability_metrics`.
3. Compare each stage's reading with the stage's success criterion. A breach:
   `traffic_manager_rollback` at once, `servicenow_incident_create` (severity 2), and stop (no
   later stage, no registration). No reading for a criterion's metric (no traffic) is a breach,
   never a pass. On a later attempt after a rollback, never deploy again: report the rollback;
   people decide the rework (the stage control fails and the run escalates to them).
4. After the last stage: `servicenow_read` (`kind: incident`) for hypercare;
   `agent_registry_write` (name, version, package_hash, owner, autonomy_level, status `live`) and
   `cmdb_write` (the service, its package and owner).

## Steps per artifact

1. **deployment_log** (`stage, start, end, traffic_pct, result`): one row per stage run, `result`
   `pass` or `fail` (a rollback is a `rollback` row).
2. **env_config_verification** (`check, expected, actual, result`): the deployed package against
   T6's `deployment_package`, and the split after each change, from `cd_status` and the traffic
   results.
3. **stage_metrics** (`key, stage, metric, threshold, actual, result`): one row per stage and
   criterion metric; `key` is `<stage>:<metric>`; `actual` copied from the stage's
   `observability_metrics` reading ("not measured" when absent, and `result` `fail`).
4. **smoke_results** (`case_id, result`): one row per stage, `traffic:<stage>`, `pass` when the
   stage's reading shows answered requests and no failed or timed-out ones.
5. **hypercare_log** (`incident_id, severity, opened, closed, resolution`): this use case's
   incidents from `servicenow_read` (severity as `sev<n>`), or one row `none`.
6. **registry_entry** (`agent_id, version, owner, autonomy_level`): copied from the
   `agent_registry_write` answer and what you wrote (`agent_id` is the registry id `AG-<n>`).
7. **handover_acceptance**: never write it; the approvers' sign-off is the acceptance.
