# Tasks: End-to-End Demo

**Input**: Design documents from `specs/014-e2e-demo/` (spec, plan, research, data-model,
contracts, quickstart)

**Tests**: TDD for the platform code (constitution IX): script loading and validation, step
expectations, the trace report and the route-fault gating are tested first. CI runs `make check`;
the relevant suites run locally. Live checks run on the demo stack.

**Format**: `[ID] [P?] [Story] Description` — `[P]` = different files, no dependency on an
unfinished task.

---

## Phase 1: Setup

- [X] T001 Move the rehearsed reply programs from `tests/support/acting_scripts.py` to `demo/rehearsed/` (one module per acting terminal plus shared helpers), keep `tests/support/acting_scripts.py` as a re-export so every existing test is unchanged; `demo/README.md` stub; `demo/` included in the orchestrator image build context only for the demo (mounted by `make demo`).
- [X] T002 [P] Console script `adlc-demo` (`src/adlc/demo/__main__.py`) in `pyproject.toml`; package skeleton `src/adlc/demo/__init__.py`.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T003 [P] `tests/unit/demo/test_script.py`: `demo/script.yaml` loads and validates per data-model.md (every step has a number, a terminal, actions of known kinds with their fields, `proves` from D-1..D-9, an expectation); every D-1..D-9 is proven by at least one step; unknown action kinds and roles not in the role catalogue are refused with the step number.

### Implementation

- [X] T004 `src/adlc/demo/script.py`: the script model and loader (no terminal or use-case names in code).
- [X] T005 `demo/script.yaml`: the ten SA §21 steps plus the D-4 escalation step and the dashboard checkpoints (D-4 on a second, short use case: T0 → T1 rejected until it escalates, then completed by a person, so the main journey stays clean; each step names its `usecase` key, analysis A2), with roles, comments, root causes, waiver fields and expectations; the T1 rework and T2 clarification recordings added to `demo/recordings/it-service-desk/` (from the reference recordings).

**Checkpoint**: the script is data, validated.

---

## Phase 3: User Story 1 – The demo script runs end to end (P1)

- [X] T006 [P] [US1] `tests/unit/demo/test_driver.py`: step expectations evaluated against run state (state, final status, an arrow of a kind); a failed expectation stops with the step, reason and `--from-step` hint; presenter mode waits until the run shows the action done (fake clock, no keyboard); `fault` lines and the `done` answer.
- [X] T007 [US1] `src/adlc/demo/driver.py`: its own worker and gateway (rehearsed replies by default: recordings for writing agents, `demo/rehearsed` programs for acting agents; `--live` the configured profile), the change approver and monitor evaluator (as `adlc-replay`), human actions through the service operations in `--auto`, waiting in presenter mode, faults through the wrapper, `--from-step` resume from the use case's state; on a model outage in `--live`, stop naming the step and offer to rerun it from that step with rehearsed replies (analysis A4); the demo report (markdown and JSON) with D-1..D-9 and their evidence.
- [X] T008 [US1] `tests/integration/demo/test_demo_auto.py`: `adlc-demo --auto` over the fake pilot (faults applied by the test as the wrapper would) completes every step and reports D-1..D-9 each with evidence; a forced failing step stops with the resume hint.
- [X] T009 [US1] `make demo-reset` (research R-04) and `tests/unit/test_demo_reset.py`: refused unless `ADLC_ENV=demo` (exit non-zero, nothing removed), asks for confirmation, then removes platform and pilot volumes and brings the stack back with migrations, specs and accounts (analysis A1).
- [X] T010 [US1] Host wrapper `scripts/demo.py` and Makefile targets `demo`, `demo-auto`, `demo-live`: stop the orchestrator, `compose run` the driver with `demo/` mounted, relay output, answer `fault` lines by running `pilot-fault` in the pilot container, restart the orchestrator at the end.

---

## Phase 4: User Story 2 – Every demo moment has a scenario test (P1)

- [ ] T011 [P] [US2] `tests/scenario/test_d1_agent_reviewer_human.py`: over the reference replay, every terminal has an agent attempt, a reviewer recommendation and a person's decision recorded (D-1).
- [ ] T012 [P] [US2] `tests/scenario/test_d6_hash_integrity.py`: the deployed hash equals T3's candidate, T4's and T5's bound hash and T6's deployment package (D-6).
- [ ] T013 [P] [US2] `tests/scenario/test_d8_dashboard.py`: the dashboard's journey (lanes, arrows), activity and KPIs reflect the replayed lifecycle (D-8).
- [ ] T014 [P] [US2] `tests/scenario/test_negative_agents.py`: an agent cannot decide a run, cannot deploy an unauthorised hash, cannot raise an operational event for another use case, cannot approve a change or a waiver (SC-005).
- [ ] T015 [US2] `tests/scenario/README.md`: D-1..D-9 each mapped to its test.

---

## Phase 5: User Story 3 – Resilience on the running stack (P1)

- [ ] T016 [P] [US3] `tests/unit/orchestration/test_route_fault.py`: `ADLC_ROUTE_FAULT` makes routing of that event type fail only when `ADLC_ENV` is `dev` or `demo` (refused at start otherwise), unset by default; other event types route normally.
- [ ] T017 [US3] The route-fault hook (settings, the orchestrator's `FaultHook` wiring in `src/adlc/orchestration/__main__.py`), documented in `.env.example` as test-only.
- [ ] T018 [US3] `scripts/resilience.py` and `make resilience` (demo env only): restart mid-run, duplicate delivery, dead letter and re-queue, each with its pass condition and evidence printed.

---

## Phase 6: User Story 4 – Traceability (P2)

- [ ] T019 [P] [US4] `tests/integration/ledger/test_trace.py`: over a walked use case, every sign-off, control decision, routing event and artifact version has a spec version, actor and hash; a missing link is reported as a gap; the chain verification result is included.
- [ ] T020 [US4] `src/adlc/ledger/trace.py` and `adlc-ledger trace <usecase>`; `make trace`.

---

## Phase 7: User Story 5 – Rehearsals (P2)

- [ ] T021 [US5] Two `make demo-auto` rehearsals on a `make demo-reset` demo stack, each followed by `make trace` (100% linked, chain verified; SC-004, analysis A3) with timings logged (SC-001, A5); fixes applied; findings recorded in `demo/README.md` and convergence.

---

## Phase 8: Polish

- [ ] T022 [P] `demo/README.md`: the rehearsed reply programs are demo assets outside `src/adlc` (use-case values allowed there; the driver stays generic, analysis A6); presenter guide (steps, what to click as which role, timings, recovery), resets, rehearsal log.
- [ ] T023 Targeted suites locally (unit demo, integration demo, scenario, ledger, orchestration); push after the user's approval; CI runs `make check` (SC-006).
