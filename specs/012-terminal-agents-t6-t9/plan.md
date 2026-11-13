# Implementation Plan: Terminal Agents T6–T9

**Branch**: `012-terminal-agents-t6-t9` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

## Summary

T6–T9 become model agents acting through feature 010's tools (research R-01). The platform gains:
- a **monitor evaluator** that runs T8's declared monitors over real telemetry and raises their
  events once per breach episode (R-02, R-03);
- real **`change`, `release`, `retirement`** evidence from the ITSM, IAM, CMDB and registry mocks
  (R-04), and a **change-approval** inbox action (R-05);
- **observability results as evidence**, so T7's copied stage metrics are checked (R-06);
- an inbox action to confirm or dismiss **agent-proposed events** (R-02);
- **platform-built artifacts** `T4.eval_baseline` and `T6.gate_evidence_summary` (R-09), so
  baselines and the evidence chain are never copied by an agent.

## Technical Context

**Language/Version**: Python 3.12, uv, ruff, mypy strict, pytest.

**Dependencies**: none new.

**Storage**: migration 0010 widens `tools.tool_result.kind` (`observability`). Monitor
evaluations are policy decisions (existing log). Change decisions and event confirmations are
records (enterprise records; run activity).

**Testing**: unit (monitor episodes, evidence mapping, stage-key checks, approval rules);
integration (T6–T9 with scripted replies through the runtime and the bridge over the fake pilot;
monitor evaluator raising drift on the model swap; change approval API; proposed-event
confirmation); scenario (reference through T9). CI runs `make check`.

**Settings**: `ADLC_MONITOR_INTERVAL` (default 1 min, real time: the time scale shrinks days to seconds and would make it a busy loop).

**Constraints**: no terminal, monitor or role names in code; agents never sign; events raised by
monitors or confirmed by people only.

## Constitution Check

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Monitors, events, roles and controls come from specs and catalogues | Pass |
| III Agents build, humans decide | Release authorisation, handover, change approval and proposed events are people's decisions | Pass |
| IV Separation of duties | Tools by scope; only the T6 hash deployable; kill switch released by a person | Pass |
| V Evidence-first | Monitor evaluations logged; observability results stored; change decisions recorded | Pass |
| VI Deterministic first | Events from declared monitors; stage checks and rollback rules deterministic | Pass |
| VII Interfaces | Evidence from mocks behind the same interfaces as the real systems | Pass |
| X Observable | Monitor evaluations traced and logged | Pass |
| XI Secure | Service token per use case for telemetry; approvals need the registry's owner role | Pass |
| XII Simplicity | Reuse of the policy engine, operational events and mocks | Pass |

**Post-design re-check**: Pass.

## Project Structure

```text
specs/012-terminal-agents-t6-t9/  plan.md research.md data-model.md quickstart.md contracts/ checklists/
adlc-specs/prompts/t6-readiness-agent.md t7-deployment-agent.md t8-operations-agent.md t9-evolution-agent.md
adlc-specs/playbooks/ (T6–T9 playbooks)  adlc-specs/shared/agents.yaml  adlc-specs/terminals/T6–T9.yaml
src/adlc/orchestration/monitors.py      # monitor evaluator (worker loop; any spec declaring monitors)
src/adlc/policy/built_artifacts.py      # signed_record, baseline, gate_summary built from records
src/adlc/policy/pilot_evidence.py       # telemetry source
src/adlc/policy/enterprise_evidence.py  # change, release, retirement sources
src/adlc/api/routes_changes.py  src/adlc/inbox/* src/adlc/ui/pages/*   # change approval, proposed events
src/adlc/tools/catalogue.py             # observability_metrics as evidence
db/migrations/versions/0010_observability_evidence.py
data/reference_usecases/it-service-desk.yaml   tests/support/acting_scripts.py (T6–T9)
```

## Complexity Tracking

| Choice | Why | Simpler alternative rejected because |
| --- | --- | --- |
| A monitor evaluator in the worker | Declared monitors must raise events (FR-007) | Bridge monitors know no spec, no evidence and no events |
