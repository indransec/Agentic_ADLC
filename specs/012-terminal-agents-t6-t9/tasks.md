# Tasks: Terminal Agents T6–T9

**Input**: Design documents from `specs/012-terminal-agents-t6-t9/` (spec, plan, research, data-model,
contracts, quickstart)

**Tests**: TDD for the core (constitution IX): evidence sources, the monitor evaluator, the
change-approval and proposed-event rules are tested first. CI runs `make check`; the relevant
suites run locally while working.

**Format**: `[ID] [P?] [Story] Description` — `[P]` = different files, no dependency on an
unfinished task.

---

## Phase 1: Setup

- [X] T001 Settings `ADLC_MONITOR_INTERVAL` (default `1min`, real time, not scaled) in `src/adlc/config/settings.py` and `.env.example`; tier step default `standard` 14 (`DEFAULT_AGENT_LIMITS`); tests updated.
- [X] T002 [P] Migration `db/migrations/versions/0010_observability_evidence.py`: `tools.tool_result.kind` adds `observability`; grants unchanged; `observability_metrics` becomes an evidence tool (kind `observability`) in `src/adlc/tools/catalogue.py` (`EVIDENCE_KINDS`) with the catalogue contract test updated.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T003 [P] `tests/integration/policy/test_enterprise_evidence.py`: `change` (window, `window_requested`, `request_status` from the latest ITSM change of the use case), `release` (`package_sha256` from T6's `deployment_package`, `release_date` = window start) and `retirement` (`credentials_revoked`, `data_disposed`, `unowned_dependants`) per contracts/telemetry-evidence.md; no records → not available → labelled synthetic fallback.
- [X] T004 [P] `tests/unit/policy/test_telemetry_evidence.py`: `telemetry` from the bridge's observability answer: `online_eval_score`, `pii_leak_count`, `availability_pct` (answered / sent), `cost_per_task_usd`, `monitors {<signal>: reporting}` for the signals in T6's `monitoring_readiness` (reporting = data in the period); unmeasured fields absent; no traffic → configured monitors not reporting; `online_eval_score` uses the same metric as `T4.eval_baseline`.

- [X] T005 [P] `tests/unit/policy/test_built_artifacts.py`: built formats (`signed_record`, `baseline`, `gate_summary`) per research R-09: `baseline` from the candidate's recorded harness result with metric and tolerance from the terminal's parameters; `gate_summary` one row per terminal of the T6 status list (status, signers, open waivers, expiry); an agent's output for a built artifact is rejected; missing harness result → baseline not available (fails closed, never a default).

### Implementation

- [X] T006 `src/adlc/policy/enterprise_evidence.py` (`change`, `release`, `retirement` from `tools.enterprise_record` and the ledger) wired into `ChainEvidenceProvider` in `src/adlc/policy/evidence.py`.
- [X] T007 Built artifacts: move the 011 signed-record building into `src/adlc/policy/built_artifacts.py` with `baseline` and `gate_summary`; `src/adlc/agents/output.py` rejects every built format; `src/adlc/orchestration/routing.py` counts them as emitted; `adlc-specs/terminals/T4.yaml` next major declares `eval_baseline` (format `baseline`, columns `metric, value, tolerance`) and parameters `baseline_metric`, `baseline_tolerance`; spec schema and toolkit accept the formats.
- [X] T008 `telemetry` in `src/adlc/policy/pilot_evidence.py` (bridge observability with the use-case service token); `adlc-specs/shared/evidence_sources.yaml` next major version with the field lists of contracts/telemetry-evidence.md.

**Checkpoint**: T6–T9 controls read real records when the tools ran; synthetic otherwise, labelled; `T4.eval_baseline` is a number from the candidate's measured result.

---

## Phase 3: User Story 1 – T6 verifies the evidence chain and prepares the release (P1)

- [ ] T009 [P] [US1] `tests/unit/inbox/test_change_approval.py` and `tests/integration/api/test_changes_api.py` per contracts/api-changes.md: only the registry's servicenow `owner_role` may decide (`403` otherwise); approve/reject writes a new ITSM record version (`status`, `decided_by`, `decided_at`, `comment`); a second decision `409`; listing shows only undecided changes; no session `401`.
- [ ] T010 [US1] Change approval: `src/adlc/inbox/service.py` (rule from the MCP registry, no role names in code), `src/adlc/api/routes/changes.py` (`GET /api/changes`, `POST /api/changes/{change_id}/decision`), inbox section "Change requests" in `src/adlc/ui/pages/inbox.py`. A decision calls `OrchestratorService.awaited_action_done` so runs waiting on it re-run their controls (research R-11).
- [ ] T011 [P] [US1] Prompt `adlc-specs/prompts/t6-readiness-agent.md` 1.0.0 and real content in `adlc-specs/playbooks/t6-release-readiness.md` and `progressive-rollout.md` (1.1.0): summarise gate evidence from the evidence block, raise the change with a window starting at approval (research R-10), configure monitors covering T1 KPIs and T2 observability, name T3's candidate as the deployment package, never write the release authorisation or the gate evidence summary (built, R-09).
- [ ] T012 [US1] `adlc-specs/shared/agents.yaml` 7.0.0: `t6-readiness-agent` model agent (standard tier) bound to T6's scopes; `adlc-specs/terminals/T6.yaml` next major (playbook versions; an evidence control `rows_match_value` on `monitoring_readiness` against recorded monitoring configuration). T6 also declares `gate_evidence_summary` as `gate_summary` (built) and CTL-T6-07 with `awaits: change approval` (R-11).
- [ ] T013 [US1] Scripted T6 replies in `tests/support/acting_scripts.py` (`Readiness`), and `tests/integration/agents/test_t6_agent.py`: after T5 the agent raises the change and configures monitors; controls fail until the change is approved in the inbox, then pass; a waiver expiring before the release date fails CTL-T6-02 naming it; `gate_evidence_summary` is built from statuses, sign-offs and waivers (agent output for it rejected); `release_authorisation` comes from sign-offs; `deployment_package` sha256 equals T3's candidate.

**Checkpoint**: T6 closes on real change and release evidence; people approve the change and sign the release.

---

## Phase 4: User Story 2 – T7 deploys the authorised hash and hands it over (P1)

- [ ] T014 [P] [US2] Prompt `adlc-specs/prompts/t7-deployment-agent.md` 1.0.0 and playbook `t7-deployment.md` 1.1.0: deploy the authorised hash, verify environment config, per stage set traffic → read observability → compare with the rollout plan's success criteria → roll back on breach; smoke cases; register in the agent registry and CMDB; never write the handover acceptance.
- [ ] T015 [US2] `agents.yaml`: `t7-deployment-agent` model agent; `adlc-specs/terminals/T7.yaml` next major: `stage_metrics` gains a `key` column (`<stage>:<metric>`) and an evidence control `rows_match_value(T7.stage_metrics, "key", "actual", observability.stages)` (recorded observability results of the run, rows keyed `<stage>:<metric>`); registry entry checked against the recorded registry record.
- [ ] T016 [US2] Scripted T7 replies (`Deployment`) and `tests/integration/agents/test_t7_agent.py`: prod-sim runs the authorised hash and `env.prod` equals T6's package (SC-001); stage metrics copied from recorded observability pass; a copied value that differs fails; a canary breach (fake pilot fault) rolls traffic back and the stage result is `fail` (SC-003); no traffic → "not measured" fails the stage check; registry and CMDB hold owner, version, autonomy level; a hypercare incident read from the ITSM mock fails CTL-T7-07 until closed; handover acceptance from sign-offs; before the change window opens the prerequisite blocks and the `window` timer reopens it.

**Checkpoint**: what T4 tested is what T7 deployed (D-6).

---

## Phase 5: User Story 3 – T8 operates the pilot and raises lifecycle events (P1)

### Tests first

- [ ] T017 [P] [US3] `tests/unit/orchestration/test_monitors.py`: a monitor's threshold evaluated through the policy engine; true after false raises the declared event once (episode rule); true after true raises nothing; unevaluable (signal not measured) never fires; the decision is logged with `check_id` = monitor id; no terminal or monitor names in code; a spec without monitors is never evaluated.
- [ ] T018 [P] [US3] `tests/unit/inbox/test_proposed_events.py` and API tests: a T8 `raised_events` row with status `proposed` appears for T8's accountable role; confirm raises the operational event (actor the person), dismiss records it; second decision `409`; other roles `403`.

### Implementation

- [ ] T019 [US3] `src/adlc/orchestration/monitors.py`: the evaluator in the worker loop (every `ADLC_MONITOR_INTERVAL`), the `monitors` of any pinned spec that declares them, once that terminal has a run (no terminal or monitor ids in code; the static check covers `monitors.py`), policy decisions on that terminal's latest run, `raise_operational_event(Actor.system("monitor"), ...)` with monitor id and measured value; traced (constitution X); wired in `src/adlc/orchestration/__main__.py`.
- [ ] T020 [US3] Proposed events: `src/adlc/inbox/service.py`, `src/adlc/api/routes/events.py` (`GET /api/events/proposed`, `POST /api/events/proposed/{run_id}/{event_id}`), inbox section in `src/adlc/ui/pages/inbox.py`; confirmation recorded as run activity `event_confirmation`.
- [ ] T021 [P] [US3] Prompt `adlc-specs/prompts/t8-operations-agent.md` 1.0.0 and playbooks `t8-operations.md`, `drift-detection.md`, `incident-response-agents.md` 1.1.0: reports from observability, monitors, ITSM and feedback; events only proposed (`status: proposed`); the kill switch invoked on a critical breach, never released.
- [ ] T022 [US3] `agents.yaml`: `t8-operations-agent` model agent; `adlc-specs/terminals/T8.yaml` next major: evidence controls `rows_match_value` on `operating_health_report` and `cost_report` against recorded observability, and on `drift_report` against the monitor decisions' measured values.
- [ ] T023 [US3] Scripted T8 replies (`Operations`) and `tests/integration/agents/test_t8_agent.py`: a review period's reports carry the recorded values; a copied cost or drift value that differs fails; a sev1 incident read from the ITSM mock fails CTL-T8-03 until closed; with the monitor evaluator, the fake pilot's model swap lowers the online score below `T4.eval_baseline`, MON-04 raises one drift event with the measured value and T9 opens (SC-002 at the test time scale).

**Checkpoint**: a model swap shows up as drift and opens T9 (D-7).

---

## Phase 6: User Story 4 – T9 classifies the change and re-enters, or retires (P1)

- [ ] T024 [P] [US4] Prompt `adlc-specs/prompts/t9-evolution-agent.md` 1.0.0 and playbooks `t9-change-impact.md`, `retirement.md` 1.1.0: classify with the change-class catalogue from the trigger evidence; re-entry terminal consistent with the class; in retire mode revoke identity and tool scopes, mark data disposed, retire the registry entry.
- [ ] T025 [US4] `agents.yaml`: `t9-evolution-agent` model agent (reasoning tier); `adlc-specs/terminals/T9.yaml` next major (playbook versions).
- [ ] T026 [US4] Scripted T9 replies (`Evolution`) and `tests/integration/agents/test_t9_agent.py`: a drift event from a model change is at least moderate and re-enters at T2 (CTL-T9-01..03); retire mode revokes through IAM, CMDB and the registry, and CTL-T9-04..06 read those records; a retirement leaving an unowned dependant fails CTL-T9-06.

---

## Phase 7: User Story 5 – Agents act only through their terminal's tools (P2)

- [ ] T027 [US5] `tests/integration/agents/test_acting_scopes.py` additions: T6 cannot deploy; T7 cannot approve the change and cannot deploy a hash other than the authorised one; T8 cannot release the kill switch; T9 outside retire mode cannot revoke; every refusal recorded, nothing reaches the fake pilot or mocks (SC-006).

---

## Phase 8: Polish & cross-cutting

- [ ] T028 Reference replay: `data/reference_usecases/it-service-desk.yaml` through T9 (`until: T9`, change approval and T8 period in the script, model swap → drift); `tests/scenario/test_reference_replay_t6_t9.py` offline with scripted replies (SC-005); `src/adlc/agents/replay.py` handles the change approval and the monitor evaluator.
- [ ] T029 [P] Pinned counts and fixtures: rules count in `tests/unit/policy/test_compiler.py` and `tests/integration/policy/test_all_rules.py`, register totals, grant tests, `scripts/make_synthetic.py` (new T7 `key` column, T6 monitoring evidence) and regenerated `data/synthetic/evidence.yaml`.
- [ ] T030 [P] Docs: `src/adlc/inbox/README.md` (change requests, proposed events), `src/adlc/orchestration/README.md` (monitor evaluator), `CONVERSION.md` notes; `data-model.md` versions as released.
- [ ] T031 Targeted suites locally (unit, agents, policy, inbox/API, scenario); push after the user's approval and let CI run `make check` (SC-007). SC-002's 10 minutes is measured only at the test time scale (live runs are not in scope, per the dev-model decision).
