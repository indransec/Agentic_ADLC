---
id: PB-T8-01
version: "1.1.0"
title: T8 operations
owner_role: adlc_coe
status: active
---
# T8 operations

## Purpose

Report, each review period, how the live agent performs against its baseline, budget, KPIs and
users, from measured readings; and surface the signals that call for a lifecycle change.

## Procedure

1. `observability_metrics` (one reading for the period), `monitoring_read` (monitors and fired
   events), `servicenow_read` (`kind: incident`), `feedback_read`.
2. A new problem without an incident: `servicenow_incident_create` (PB-T8-02).
3. `eval_store_write` a short note of the period's findings.
4. Write the artifacts.

## Steps per artifact

1. **operating_health_report** (`metric, threshold, actual, trend, status`): one row per metric
   of the reading that has a threshold (T4 baseline, T1 non-functional requirements, budget),
   `actual` copied from the reading; `status` `ok` or `breach`. Always include the `cost` and
   `tokens` rows (against the T2 budget): the cost report's values are checked through them.
2. **incident_problem_log** (`incident_id, severity, opened, closed, root_cause, linked_event`):
   this use case's incidents (severity `sev<n>`), or one row `none`.
3. **drift_report** (`metric, slice, baseline, current, delta`): per PB-T8-03; `current` copied
   from the reading.
4. **cost_report** (`period, task_count, token_count, cost_usd, budget_usd`): one row `current`
   from the reading's requests, tokens and cost; the budget from T2.
5. **kpi_scorecard** (`kpi_id, baseline, target, actual, value_realised`): one row per T1 KPI;
   `actual` "not measured" when the pilot does not measure it.
6. **feedback_themes** (`theme, volume_count, sentiment, action`): grouped from `feedback_read`.
7. **raised_events** (`event_id, event_type, raised_at, routed_to, status`): the monitors' fired
   events (`raised`), and events you propose (`proposed`, `event_id` `PROP-<n>`), or one row
   `none`.
