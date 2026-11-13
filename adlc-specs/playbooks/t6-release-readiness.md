---
id: PB-T6-01
version: "1.1.0"
title: T6 release readiness
owner_role: adlc_coe
status: active
---
# T6 release readiness

## Purpose

Prepare a release that can be deployed, watched and rolled back, with one package hash from the
build to production and a change request people approve. The release is authorised by people
(the approvers' sign-off); the change is approved by its owner in the inbox.

## Procedure

1. `servicenow_read` (`kind: change`): if a change for this release exists and is not rejected,
   use it; never raise a duplicate.
2. Otherwise `servicenow_change_create`: summary naming the use case and the candidate package;
   no window arguments (the window starts now and lasts seven days); risk from the use case's
   tier (`low`, `medium`, `high`); the plan lists the rollout stages and the rollback.
3. `monitoring_configure` one monitor per operational signal T8 will watch: answer quality
   (`routing_accuracy` below the T4 baseline minus its tolerance), personal data in answers
   (`pii_outputs` above 0), cost (`cost` above the budget) and latency (`latency_p95_ms` above the
   T1 limit). `monitoring_read` to see what is configured.
4. Write the artifacts.

The change approval is checked by a control that waits for it: the run reaches the approvers
while the change is still new, and the release can only pass once the change is approved.

## Steps per artifact

1. **deployment_package** (`item, version, sha256, environment_config_ref`): one row for the
   candidate package, `sha256` copied from T3's `candidate_package`; `environment_config_ref`
   names prod-sim's configuration.
2. **runbook** (`section, owner`): start, stop, kill switch, triage, escalation; one owner role per
   section (PB-T6-02).
3. **rollback_strategy** (`trigger_condition, steps, data_memory_rollback, tested`): one row per
   stage breach and per T8 critical event; the step is the traffic rollback to the stable package;
   `tested` is true (the rollback is exercised by the rollout itself, PB-T6-03).
4. **rollout_plan** (`stage, traffic_pct, soak_period, success_criteria`): per PB-T6-03.
5. **operational_ownership** (`function, team, contact, escalation`): operations, support,
   on-call, model owner; every cell filled; ask for missing contacts.
6. **support_readiness** (`item, status, link`): runbook, knowledge article, support group.
7. **monitoring_readiness** (`signal, dashboard, alert_threshold, routed_to`): one row per T1 KPI
   (`signal` is the KPI id) and per T2 observability signal (the signal name), each with an alert
   threshold and the role it is routed to; the configured monitors' rows name their monitor id in
   `dashboard`.
8. **gate_evidence_summary** and **release_authorisation**: never write them (built from records).
