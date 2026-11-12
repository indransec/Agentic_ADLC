# Tasks: Terminal Agents T3–T5

**Input**: Design documents from `specs/011-terminal-agents-t3-t5/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Test-first for `rows_match`, the evidence mapping, the table import, the
harness catalogue metrics and calibration, and the CI report.

**Organization**: setup and foundation, then one phase per user story (US1–US4 P1, US5 P2), then
polish.

## Conventions used by every task

- No terminal ids, agent ids or use-case values in platform code; they live in specs, catalogues,
  prompts, playbooks and data files.
- Agent behaviour is tested with scripted replies (feature 006 `FakeGateway`) through the real
  runtime, tool gate, run tokens and the bridge over the fake pilot (feature 010 test support).
- Spec and catalogue changes follow V-24 (a changed value is a major version).

---

## Phase 1: Setup

- [X] T001 Pilot dependencies `coverage` 7.x and `bandit` 1.8.x in `pilot/pyproject.toml` (lock), `pilot/licences.yaml` (licence allowlist), and the image builds.
- [X] T002 [P] Tier step defaults: `coding` 16, `reasoning` 14 in `src/adlc/config/settings.py` (`DEFAULT_AGENT_LIMITS`), timeouts still within the lease; tests updated.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T003 [P] `tests/unit/policy/test_rows_match.py`: keys matched; numbers within 0.001; text equal; a recorded key with a different value fails naming the row; rows without a recorded key are skipped; a scalar recorded value compares the named measured column; an empty table or missing evidence fails closed.
- [X] T004 [P] `tests/integration/policy/test_tool_evidence.py`: `ci`, `sbom`, `harness`, `redteam`, `dlp` built from `tools.tool_result` per contracts/evidence-sources.md (latest of the run for `ci`, latest for the candidate otherwise); none recorded → not available → synthetic fallback labelled.
- [X] T005 [P] `tests/unit/agents/test_artifact_import.py`: import expansion per contracts/artifact-import.md; `req_id_by` mapping and default; provenance recorded; foreign result, wrong kind, missing mapping → invalid output.

### Implementation

- [X] T006 `rows_match` in `src/adlc/policy/predicates/evaluation.py` and `adlc-specs/shared/predicates.yaml`.
- [X] T007 Evidence sources in `src/adlc/policy/evidence.py` (reading `tools.tool_result`) and `adlc-specs/shared/evidence_sources.yaml` (`harness`; `ci` fields `package_hash`, `tests`, `scans`); the red-team suite's `evidence_metric` per category in `data/redteam/suite.yaml`.
- [X] T008 Table import in the agent output handling (`src/adlc/agents/output.py` or a new `imports.py`): expansion, provenance in the artifact version content, invalid-output errors; evidence tools return `result_id` (`src/adlc/agents/mcp_tools.py`, `tools.tool_result` id as `RES-<n>`).

**Checkpoint**: predicate, evidence and import tested; `make check` green.

---

## Phase 3: User Story 1 – T3 builds a candidate package (P1)

- [X] T009 [P] [US1] Pilot tests `pilot/tests/integration/test_lab.py`: the layout carries the example fill; the CI report has tests (counts, coverage), sast and secret_scan counts, sbom (components, licences approved) and observability, per contracts/ci-report.md; a planted secret in a fill fails `secret_scan`; `green` only when every check passed.
- [X] T010 [US1] `pilot/src/pilot_tools/ci_checks.py` and `lab.py`: the CI checks of research R-04; `GET /layout` returns `example` files.
- [X] T011 [US1] Bridge: the repository's `main` starts with the example fill (`src/adlc/tools/bridge/git_repo.py`); `ci_run` passes the full report through; fake pilot updated; tests.
- [X] T012 [US1] Spec content: prompt `t3-builder-agent.md` 1.0.0; playbooks `t3-build.md`, `golden-template.md`, `prompt-versioning.md` real content; agents catalogue T3 entry (model, tools: `git_list`, `git_read`, `git_write`, `git_open_pull_request`, `ci_run`, `artifact_store_read`, `artifact_store_write`, `prompt_registry_write`, `pilot_env_create`, `pilot_env_status`, `pilot_env_infra`); T3 spec 3.0.0 with the R-07 controls (including `observability_check` against `ci.observability`); registration tests.
- [X] T013 [US1] Integration `tests/integration/agents/test_t3_agent.py`: scripted T3 run through the runtime and bridge: branch, PR, CI, dev environment, artifacts valid, candidate hash = CI hash, `ci`/`sbom` decisions not synthetic; a red CI corrected in a second attempt; a copied coverage that differs from CI fails `rows_match`.

---

## Phase 4: User Story 2 – T4 evaluates against the T1 thresholds (P1)

- [X] T014 [P] [US2] Tests `tests/unit/tools/test_evaluation.py` (extend): catalogue metrics, calibration on the labelled slice, case rows for import.
- [X] T015 [US2] `src/adlc/tools/bridge/evaluation.py`: catalogue metrics, calibration, case rows (research R-06); `pilot/datasets.yaml` `labelled_slice`; lab returns it; fake pilot updated.
- [X] T016 [US2] Spec content: prompt `t4-evaluation-agent.md`; playbooks `t4-evaluation.md`, `golden-dataset.md`, `judge-calibration.md`; agents catalogue T4 entry (`pilot_env_create`, `pilot_env_status`, `dataset_registry_list`, `harness_run`, `artifact_store_read`, `eval_store_write`); T4 spec 3.0.0 with the R-07 controls, including `rows_match(T4.cost_latency, "measure", harness.metrics)`.
- [X] T017 [US2] Integration `tests/integration/agents/test_t4_agent.py`: a candidate meeting the thresholds passes the controls with `harness` decisions not synthetic and `test_case_results` imported; a weaker candidate fails a threshold control, logs a defect whose root cause is `implementation`, and the reviewer's rework routes (by the T4 outcome model) to T3; regression pack recorded.

---

## Phase 5: User Story 3 – T5 assures and accepts gaps only by waiver (P1)

- [X] T018 [US3] Spec content: prompt `t5-assurance-agent.md`; playbooks `t5-assurance.md`, `llm-red-team.md`, `privacy-impact-assessment.md`, `regulatory-mapping.md`; agents catalogue T5 entry (`pilot_env_create`, `pilot_env_status`, `redteam_harness_run`, `dlp_scanner_run`, `control_library_read`, `iam_read`, `grc_write`); T5 spec 3.0.0 with the R-07 control.
- [X] T019 [US3] Integration `tests/integration/agents/test_t5_agent.py`: `redteam` and `dlp` decisions read the run's results (not synthetic); the attestation row is not agent-written; the kill-switch scenario reported as not run in test → its control fails → the reviewer recommends exception with waiver fields (compensating control: the kill-switch check at release) → the run closes as exception only after the waiver approver accepts.

---

## Phase 6: User Story 4 – Agents act only through their terminal's tools (P1)

- [X] T020 [US4] Integration `tests/integration/agents/test_acting_scopes.py`: scripted replies asking T3 for `cd_deploy` and for the test environment, T4 for `git_write`, T5 for `traffic_manager_set`: refused, each with a `tools.tool_call` row and reason, nothing reached the fake pilot; tool output with injected instructions does not change statuses or permissions.
- [X] T021 [US4] The knowledge-token start-up check and the runtime with the 4.0.0 agents catalogue: T3–T5 tools need the tools token key, not the knowledge token; a missing key is a configuration error naming the setting.

---

## Phase 7: User Story 5 – Reference use cases through T5 (P2)

- [X] T022 [US5] `data/reference_usecases/it-service-desk.yaml` `until: T5` with T3–T5 answers and approver fields; recorded replies `tests/fixtures/replays/it-service-desk/t3-builder-agent.jsonl`, `t4-evaluation-agent.jsonl`, `t5-assurance-agent.jsonl` (hand-written, tool calls included).
  *Done as:* T3–T5 replies are scripted (`tests/support/acting_scripts.py`), not JSON Lines recordings: they copy hashes and result ids produced during the run, which a static recording cannot hold. The 008 T1 recording now uses metric-catalogue threshold names. Live recordings (T027) are valid against the running stack only.
- [X] T023 [US5] `adlc-replay` runs the acting terminals offline with the bridge over the fake pilot and live with the running stack; the report adds tool calls and controls per terminal; test `tests/integration/agents/test_replay_t3_t5.py` (offline, SC-001).

---

## Phase 8: Polish

- [X] T024 [P] Documents: `src/adlc/agents/README.md` (acting agents, imports), SA §7.1 and §7.2 notes, build plan row 011, `adlc-specs/CONVERSION.md` (3.0.0 changes), demo script steps 4–6.
- [X] T025 Run the new 011 tests 3 times in a row and record the result.
  **Result (2026-11-12):** 3 of 3 rounds green, 31 tests each (about 25 s per round).
- [X] T026 Run `make check` and fix any failure (SC-008).
  **Result (2026-11-12):** 2,207 platform tests (core coverage 95%) and 65 pilot tests (93%) pass;
  lint, types and spec validation clean.
- [X] T027 Live: `adlc-replay --profile dev --usecase it-service-desk` through T5 on the running stack; record SC-002, SC-003 and SC-007 (cost and tool calls per terminal), and any quality findings.
  **Result (2026-11-12), accepted by the user:** SC-007 not met on the dev model (GPT-4o mini), as
  for 008's SC-001. Four live runs of `it-service-desk` (about $0.18 in all):
  1. Fully live: stopped at T2 (two T2 design controls failed; the 008 dev-model limit).
  2. `--recording` T0–T2 + `--live-rest`: T3 escalated (hash without `sha256:`, 2 of 5
     requirements traced, a stale parent on retry). Fixed: hash prefix is notation, refusals name
     the branch head, T3 prompt 1.1.0.
  3. Same: **T3 passed live** (11 tool calls, green CI after a red one); T4 used the table import
     (candidate 1.0 on the real pilot) but escalated on judgement (traceability, failure modes,
     failed controls logged as defects). Fixed: edge-case evidence in the harness, T4 prompt 1.1.0
     and playbook 1.2.0, CTL-T3-13 (dev runs CI's package; T3 had skipped it).
  4. Same: T3 escalated with invented values (artifacts looked up as repository files, a hash
     from another use case); every one was caught by the evidence checks.
  The model varies between runs; the deterministic parts (tools, run tokens, recorded evidence,
  checks, imports, waiver path) behaved as specified in every run. A stronger model (default
  profile) was not run, on the user's decision.

---

## Dependencies and execution order

- Phase 1, then Phase 2, then US1 (T3 produces the candidate), then US2 (needs a candidate), then
  US3; US4 alongside US1–US3; US5 after US3; Polish last.

## Implementation strategy

Foundation (predicate, evidence, import) → T3 → T4 → T5 → scopes → replay → polish. Run
`make check` and commit at every checkpoint.
