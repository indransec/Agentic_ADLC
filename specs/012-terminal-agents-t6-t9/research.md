# Research: Terminal Agents T6–T9 (feature 012)

## R-01 Agents, prompts, playbooks

**Decision.** `t6-readiness-agent`, `t7-deployment-agent`, `t8-operations-agent` (standard tier)
and `t9-evolution-agent` (reasoning) become model agents (agents catalogue 7.0.0) with new prompts
(1.0.0) and real content for their playbooks (1.1.0), bound to the tools their terminal's scopes
allow; specs T6–T9 move to their next major versions. The `standard` tier gets 14 steps (T7 steps
through deploy, three stages, smoke and registration).

## R-02 T8's declared monitors raise the lifecycle events (FR-007)

**Decision.** The T8 spec already declares its monitors (`MON-01`..`MON-07`): a signal, a threshold
written as a policy expression over `telemetry` (and T1/T2/T4 evidence) and the event it raises.
A **monitor evaluator** in the orchestrator worker evaluates, every `ADLC_MONITOR_INTERVAL`, the
monitors of every use case whose T8 has started, through the policy engine (each evaluation is a
policy decision with check id `MON-xx`). When a monitor's threshold becomes true it raises the
declared operational event (`raise_operational_event`, actor `system:monitor`) with the monitor
id and measured value — once per breach episode (the previous decision for that monitor was not a
breach). A threshold that cannot be evaluated (signal not measured) never fires.

**Rationale.** Spec-driven (constitution I), deterministic (VI), and the decision log records why
an event was raised (V). No terminal or monitor names in code.

**Agent-proposed events.** The T8 agent's `raised_events` rows with status `proposed` appear in the
inbox of T8's accountable role; a person confirms (raises) or dismisses each (new inbox action).

## R-03 Real `telemetry` evidence

**Decision.** The pilot evidence source (feature 010) answers `telemetry` from the bridge's
observability (service token with the use case): `online_eval_score` = routing accuracy,
`pii_leak_count`, `availability_pct` (answered / sent), `cost_per_task_usd`, and `monitors`
(`{<monitor id>: reporting}` where reporting = its signal's value is present). Fields the pilot does
not measure (policy violations, KPI values, autonomy breaches, upstream notices) are absent, so
their monitors do not fire.

## R-04 Real `change`, `release`, `retirement` evidence (FR-010)

**Decision.** The SQL evidence provider reads the use case's enterprise records (feature 010):

| Source | From |
| --- | --- |
| `change` | Latest ITSM change of the use case: `window {start, end}`, `window_requested` (a window exists), `request_status` (`new`, `approved`, `rejected`) |
| `release` | `package_sha256`: T6's `deployment_package` sha256; `release_date`: the change window start |
| `retirement` | `credentials_revoked`: IAM revocations cover identity and tool scopes; `data_disposed`: the CMDB item of the agent has `data_status: disposed`; `unowned_dependants`: registry entries naming this agent in `depends_on` with no owner |

## R-05 Change approval in the inbox (FR-012)

**Decision.** `POST /api/changes/{change_id}/decision {approve, comment}` and an inbox section
"Change requests". Allowed role: the `servicenow` server's `owner_role` in the MCP registry (spec
content, `release_manager` today). The decision is a new version of the ITSM record (`status`,
`decided_by`, `decided_at`, `comment`) — append-only, like every mock record.

## R-06 T7 stages and their evidence (FR-005, SC-003)

**Decision.** `observability_metrics` becomes an evidence tool (kind `observability`, migration
0010 widens the kind check). The T7 agent: `cd_deploy` → `traffic_manager_set shadow` → read
metrics → `canary` at the plan's share → read → `full` → read; a stage whose metric breaches the
plan's success criterion → `traffic_manager_rollback` and the stage result `fail`. Copied stage
metrics are checked against the recorded observability results (`rows_match_value`, keyed by
`<stage>:<metric>` via a stage column the agent writes). Stage soak periods are scaled by the
demo time scale.

## R-07 T9 classification and retirement

**Decision.** The T9 agent reads the trigger evidence (the event's monitor and value), classifies
with the change-class catalogue (existing controls `class_at_least_if`, `reentry_consistent`), and
in retire mode calls `iam_revoke` (identity and tool scopes), `cmdb_write` (`data_status:
disposed`) and `agent_registry_write` (`status: retired`).

## R-08 Replay

**Decision.** The incident-triage reference runs until T9 (offline, scripted acting replies, the
monitor evaluator on): T7 releases, T8's first review, the model swap on the fake pilot, the drift
event from MON-04, T9 classifies and re-enters at T2. Approver fields supply `eval_baseline` at T4.
