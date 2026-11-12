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

- [ ] T001 Settings `ADLC_MONITOR_INTERVAL` (default `1m`, scaled by `ADLC_TIME_SCALE`) in `src/adlc/config/settings.py` and `.env.example`; tier step default `standard` 14 (`DEFAULT_AGENT_LIMITS`); tests updated.
- [ ] T002 [P] Migration `db/migrations/versions/0010_observability_evidence.py`: `tools.tool_result.kind` adds `observability`; grants unchanged; `observability_metrics` becomes an evidence tool (kind `observability`) in `src/adlc/tools/catalogue.py` (`EVIDENCE_KINDS`) with the catalogue contract test updated.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [ ] T003 [P] `tests/integration/policy/test_enterprise_evidence.py`: `change` (window, `window_requested`, `request_status` from the latest ITSM change of the use case), `release` (`package_sha256` from T6's `deployment_package`, `release_date` = window start) and `retirement` (`credentials_revoked`, `data_disposed`, `unowned_dependants`) per contracts/telemetry-evidence.md; no records → not available → labelled synthetic fallback.
- [ ] T004 [P] `tests/unit/policy/test_telemetry_evidence.py`: `telemetry` from the bridge's observability answer: `online_eval_score`, `pii_leak_count`, `availability_pct` (answered / sent), `cost_per_task_usd`, `monitors {<id>: reporting}`; unmeasured fields absent; no traffic → monitors not reporting.

### Implementation

- [ ] T005 `src/adlc/policy/enterprise_evidence.py` (`change`, `release`, `retirement` from `tools.enterprise_record` and the ledger) wired into `ChainEvidenceProvider` in `src/adlc/policy/evidence.py`.
- [ ] T006 `telemetry` in `src/adlc/policy/pilot_evidence.py` (bridge observability with the use-case service token); `adlc-specs/shared/evidence_sources.yaml` next major version with the field lists of contracts/telemetry-evidence.md.

**Checkpoint**: T6–T9 controls read real records when the tools ran; synthetic otherwise, labelled.

---

## Phase 3: User Story 1 – T6 verifies the evidence chain and prepares the release (P1)

- [ ] T007 [P] [US1] `tests/unit/inbox/test_change_approval.py` and `tests/integration/api/test_changes_api.py` per contracts/api-changes.md: only the registry's servicenow `owner_role` may decide (`403` otherwise); approve/reject writes a new ITSM record version (`status`, `decided_by`, `decided_at`, `comment`); a second decision `409`; listing shows only undecided changes; no session `401`.
- [ ] T008 [US1] Change approval: `src/adlc/inbox/service.py` (rule from the MCP registry, no role names in code), `src/adlc/api/routes/changes.py` (`GET /api/changes`, `POST /api/changes/{change_id}/decision`), inbox section "Change requests" in `src/adlc/ui/pages/inbox.py`.
- [ ] T009 [P] [US1] Prompt `adlc-specs/prompts/t6-readiness-agent.md` 1.0.0 and real content in `adlc-specs/playbooks/t6-release-readiness.md` and `progressive-rollout.md` (1.1.0): summarise gate evidence from the evidence block, raise the change with the window, configure monitors covering T1 KPIs and T2 observability, name T3's candidate as the deployment package, never write the release authorisation.
- [ ] T010 [US1] `adlc-specs/shared/agents.yaml` 7.0.0: `t6-readiness-agent` model agent (standard tier) bound to T6's scopes; `adlc-specs/terminals/T6.yaml` next major (playbook versions; an evidence control `rows_match_value` on `monitoring_readiness` against recorded monitoring configuration).
- [ ] T011 [US1] Scripted T6 replies in `tests/support/acting_scripts.py` (`Readiness`), and `tests/integration/agents/test_t6_agent.py`: after T5 the agent raises the change and configures monitors; controls fail until the change is approved in the inbox, then pass; a waiver expiring before the release date fails CTL-T6-02 naming it; `release_authorisation` comes from sign-offs; `deployment_package` sha256 equals T3's candidate.

**Checkpoint**: T6 closes on real change and release evidence; people approve the change and sign the release.

---

## Phase 4: User Story 2 – T7 deploys the authorised hash and hands it over (P1)

- [ ] T012 [P] [US2] Prompt `adlc-specs/prompts/t7-deployment-agent.md` 1.0.0 and playbook `t7-deployment.md` 1.1.0: deploy the authorised hash, verify environment config, per stage set traffic → read observability → compare with the rollout plan's success criteria → roll back on breach; smoke cases; register in the agent registry and CMDB; never write the handover acceptance.
- [ ] T013 [US2] `agents.yaml`: `t7-deployment-agent` model agent; `adlc-specs/terminals/T7.yaml` next major: `stage_metrics` gains a `key` column (`<stage>:<metric>`) and an evidence control `rows_match_value(T7.stage_metrics, "key", "actual", <recorded observability>)`; registry entry checked against the recorded registry record.
- [ ] T014 [US2] Scripted T7 replies (`Deployment`) and `tests/integration/agents/test_t7_agent.py`: prod-sim runs the authorised hash and `env.prod` equals T6's package (SC-001); stage metrics copied from recorded observability pass; a copied value that differs fails; a canary breach (fake pilot fault) rolls traffic back and the stage result is `fail` (SC-003); no traffic → "not measured" fails the stage check; registry and CMDB hold owner, version, autonomy level; handover acceptance from sign-offs.

**Checkpoint**: what T4 tested is what T7 deployed (D-6).

---

## Phase 5: User Story 3 – T8 operates the pilot and raises lifecycle events (P1)

### Tests first

- [ ] T015 [P] [US3] `tests/unit/orchestration/test_monitors.py`: a monitor's threshold evaluated through the policy engine; true after false raises the declared event once (episode rule); true after true raises nothing; unevaluable (signal not measured) never fires; the decision is logged with `check_id` = monitor id; no terminal or monitor names in code.
- [ ] T016 [P] [US3] `tests/unit/inbox/test_proposed_events.py` and API tests: a T8 `raised_events` row with status `proposed` appears for T8's accountable role; confirm raises the operational event (actor the person), dismiss records it; second decision `409`; other roles `403`.

### Implementation

- [ ] T017 [US3] `src/adlc/orchestration/monitors.py`: the evaluator in the worker loop (every `ADLC_MONITOR_INTERVAL`), monitors from the pinned spec of every use case whose T8 has started, policy decisions on the latest T8 run, `raise_operational_event(Actor.system("monitor"), ...)` with monitor id and measured value; traced (constitution X); wired in `src/adlc/orchestration/__main__.py`.
- [ ] T018 [US3] Proposed events: `src/adlc/inbox/service.py`, `src/adlc/api/routes/events.py` (`GET /api/events/proposed`, `POST /api/events/proposed/{run_id}/{event_id}`), inbox section in `src/adlc/ui/pages/inbox.py`; confirmation recorded as run activity `event_confirmation`.
- [ ] T019 [P] [US3] Prompt `adlc-specs/prompts/t8-operations-agent.md` 1.0.0 and playbooks `t8-operations.md`, `drift-detection.md`, `incident-response-agents.md` 1.1.0: reports from observability, monitors, ITSM and feedback; events only proposed (`status: proposed`); the kill switch invoked on a critical breach, never released.
- [ ] T020 [US3] `agents.yaml`: `t8-operations-agent` model agent; `adlc-specs/terminals/T8.yaml` next major: evidence control `rows_match_value` on `operating_health_report` against recorded observability.
- [ ] T021 [US3] Scripted T8 replies (`Operations`) and `tests/integration/agents/test_t8_agent.py`: a review period's reports carry the recorded values; a sev1 incident fails CTL-T8-03 until closed; with the monitor evaluator, the fake pilot's model swap lowers the online score below `T4.eval_baseline`, MON-04 raises one drift event with the measured value and T9 opens (SC-002 at the test time scale).

**Checkpoint**: a model swap shows up as drift and opens T9 (D-7).

---

## Phase 6: User Story 4 – T9 classifies the change and re-enters, or retires (P1)

- [ ] T022 [P] [US4] Prompt `adlc-specs/prompts/t9-evolution-agent.md` 1.0.0 and playbooks `t9-change-impact.md`, `retirement.md` 1.1.0: classify with the change-class catalogue from the trigger evidence; re-entry terminal consistent with the class; in retire mode revoke identity and tool scopes, mark data disposed, retire the registry entry.
- [ ] T023 [US4] `agents.yaml`: `t9-evolution-agent` model agent (reasoning tier); `adlc-specs/terminals/T9.yaml` next major (playbook versions).
- [ ] T024 [US4] Scripted T9 replies (`Evolution`) and `tests/integration/agents/test_t9_agent.py`: a drift event from a model change is at least moderate and re-enters at T2 (CTL-T9-01..03); retire mode revokes through IAM, CMDB and the registry, and CTL-T9-04..06 read those records; a retirement leaving an unowned dependant fails CTL-T9-06.

---

## Phase 7: User Story 5 – Agents act only through their terminal's tools (P2)

- [ ] T025 [US5] `tests/integration/agents/test_acting_scopes.py` additions: T6 cannot deploy; T7 cannot approve the change and cannot deploy a hash other than the authorised one; T8 cannot release the kill switch; T9 outside retire mode cannot revoke; every refusal recorded, nothing reaches the fake pilot or mocks (SC-006).

---

## Phase 8: Polish & cross-cutting

- [ ] T026 Reference replay: `data/reference_usecases/it-service-desk.yaml` through T9 (`until: T9`, change approval and T8 period in the script, model swap → drift); `tests/scenario/test_reference_replay_t6_t9.py` offline with scripted replies (SC-005); `src/adlc/agents/replay.py` handles the change approval and the monitor evaluator.
- [ ] T027 [P] Pinned counts and fixtures: rules count in `tests/unit/policy/test_compiler.py` and `tests/integration/policy/test_all_rules.py`, register totals, grant tests, `scripts/make_synthetic.py` (new T7 `key` column, T6 monitoring evidence) and regenerated `data/synthetic/evidence.yaml`.
- [ ] T028 [P] Docs: `src/adlc/inbox/README.md` (change requests, proposed events), `src/adlc/orchestration/README.md` (monitor evaluator), `CONVERSION.md` notes; `data-model.md` versions as released.
- [ ] T029 Targeted suites locally (unit, agents, policy, inbox/API, scenario); push after the user's approval and let CI run `make check` (SC-007).
