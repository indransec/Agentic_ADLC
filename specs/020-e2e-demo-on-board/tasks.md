---

description: "Task list for 020-e2e-demo-on-board"
---

# Tasks: End-to-End Demo on the Board

**Input**: Design documents from `specs/020-e2e-demo-on-board/` (spec, plan, research, data-model, contracts, quickstart)

**Prerequisites**: plan.md and spec.md (Gate 1 and Gate 2 approved 2026-11-21)

**Tests**: Requested. Test first for the mapping, classify, desired, the script validation, the tokens file and the token import.

**Organization**: by user story (spec US1–US5), after a setup and a foundational phase. US2 (the change kind) is foundational for the demo, so it comes first.

## Format: `[ID] [P?] [Story] Description`

- Paths are relative to the repository root; the simulator's work is in `ado_sim/` (`env -u VIRTUAL_ENV uv run ...` from there).

---

## Phase 1: Setup

- [X] T001 Simulator seed `ado_sim/seed/demo.yaml`: the `Change Request` type (states `Awaiting approval` / Proposed, `Approved` / Completed, `Rejected` / Removed; the ADLC fields), its `form` section (Decision: decision, comment; Change: title, state, description), and Approve change and Reject change in the decision field's allowed values; review the 015 fixtures this changes; `make ado-sim-check`
- [X] T002 Tracker mapping `adlc-specs/tracker_mapping.yaml` per data-model.md (`items.change`, the two decision values, `platform_written.change`) and its schema `adlc-specs/schema/catalogues/tracker_mapping.schema.json` (`items.change` and `platform_written.change` required); `tests/contract/board/test_decision_values.py` passes with nine values

---

## Phase 2: Foundational – the change kind (US2, P1)

- [X] T003 [US2] Spec toolkit tests first (`tests/unit/spec_toolkit/` or the tracker mapping rules' test module): the mapping with the change kind is valid; missing `items.change` → V-32; a change state left out → V-34; then `src/adlc/spec_toolkit/rules/tracker_mapping.py` (V-34 covers `items.change.states`: awaiting, approved, rejected)
- [X] T004 [US2] Mapping tests first (`tests/unit/engagement/test_mapping.py`): `KINDS` includes `change`; the change's type, fields, states, platform-written fields; `kind_of_type("Change Request") == "change"`; which decision values belong to runs and which to changes; then `src/adlc/engagement/mapping.py`
- [X] T005 [US2] Desired tests first (`tests/unit/engagement/test_desired.py`): `ChangeSnapshot` on a run gives one change item under the run's item: title, description (summary, package hash, the waiting run, the deciding role, escaped), state per record state (`new` → awaiting, `approved`, `rejected`), change id; every change of a run has an item; then `src/adlc/engagement/desired.py` (`ChangeSnapshot`, `RunSnapshot.changes`, the item, `snapshot()` reading the run's change records through `ChangeService`)
- [X] T006 [US2] Classify tests first (`tests/unit/engagement/test_classify.py`): a new change value in a change item's decision field → `DECIDE_CHANGE`; a run value on a change item and a change value on a run item → refused `unknown_value` naming the allowed ones; a person's change to a change item's platform-written field → revert; then `src/adlc/engagement/classify.py` and `src/adlc/engagement/inputs.py` as needed
- [X] T007 [US2] Integration tests first in `tests/integration/engagement/test_change.py` (016 rig, fake board): a change raised for a run appears under the run item; the ITSM owner role approves it on the board → the change record is decided by that person, the run's controls re-run, the item Approved, the outcome `accepted` with command `decide_change:approve`, `source` recorded; reject likewise; another role → refused `not_authorised` with a comment and the field cleared; a second decision → refused `stale`; reconciliation restores a drifted change item; then `src/adlc/engagement/inbound.py` (apply through `ChangeService.decide`) and `src/adlc/engagement/wiring.py` (the change service in the engagement layer)
- [X] T008 [US2] The board check (`adlc-board check-mapping`) covers the new type, its states and fields: extend its test in `tests/integration/engagement/test_mapping_check.py` (a board without `Change Request` reports the gap); 019's `/board/items/change/{id}` answers for a projected change (add a case to `tests/integration/api/test_board_routes.py`)

---

## Phase 3: User Story 1 – The demo, decided on the board (P1) 🎯 MVP

- [X] T009 [US1] Simulator `ado-sim token import <unique_name> --stdin` (tests first in `ado_sim/tests/unit/test_cli.py`: registers a token of 40+ characters, the user can call the API with it; refused for a short token, an unknown or inactive user, a token already registered; the token never in the output); `ado_sim/src/ado_sim/cli.py`; `ado_sim/contract/differences.md` (ADO lets nobody choose a token)
- [X] T010 [US1] Tokens file tests first (`tests/unit/demo/test_board_tokens.py`): created with a random token per mapped board identity when missing, mode 600, read back; never logged; then `scripts/demo_board.py` (create or read the file at `ADLC_DEMO_BOARD_TOKENS`; import the sync's token from `ADLC_BOARD_TOKEN` and each person's into the simulator over stdin; set the page passwords from `ADO_SIM_DEMO_PASSWORD`) and `make demo-reset` calling it after `make up`; `.env.example`: `ADLC_DEMO_BOARD_TOKENS` (demo only)
- [X] T011 [US1] Script tests first (`tests/unit/demo/test_script.py`): `MOMENTS` gains D-12 and D-13; actions `board_change` {role, item, field, value}, `drift` {item, field, value}, `reconcile`; expectations `reverted`, `reconciled`; invalid ones refused naming the step; then `src/adlc/demo/script.py`
- [X] T012 [US1] The board actor `src/adlc/demo/board.py`: a `BoardAdapter` per demo person (their token, the ADO adapter; a factory the tests replace with the fake board's `as_user`), finding a step's items through 016's links (waiting at most two poll intervals plus processing, then a step failure naming the item), turning each action into a board write with the mapping's fields and values (submit → an Epic in the mapping's area; pass, reject, exception, complete_escalation, waiver decisions, approve_change → the decision field with comment and inputs as fields or Values lines; answer → the clarification's answer field; board_change → the named field as the role; drift → the field with the service account; reconcile → the engagement layer's reconciliation as the CoE), and the presenter's text (the user, the item's address, the value and every input)
- [X] T013 [US1] Driver tests first in `tests/integration/demo/test_board_mode.py` (stub agents, the fake board, the board actor's factory replaced): each action kind becomes a board change by the named person (simulator-side history on the fake board; run activity with `source`); presenter mode prints the item address and values and waits; the D-12 and D-13 steps meet `reverted` and `reconciled`; the whole script's auto run passes in board mode; with the sync off, 014's demo tests unchanged; then `src/adlc/demo/driver.py` and `src/adlc/demo/__main__.py` (board mode when the board settings are enabled; the report lists D-12 and D-13 with items and the reconciliation)

---

## Phase 4: User Stories 3 and 4 – D-12 and D-13 in the script (P2)

- [X] T014 [US3] [US4] `demo/script.yaml`: the D-12 step after the main journey's T1 sign-off (the product owner sets the Epic's state to T5 on the board; expect `reverted`), the D-13 step before T9 (the operator drifts the Epic's sub-stage; the CoE reconciles; expect `reconciled`); step 10's change approval stays `approve_change` (now on the board); renumber and keep `FROM_STEP` meaningful

---

## Phase 5: User Story 5 – Rehearsal and readiness (P2)

- [X] T015 [P] [US5] `demo/README.md`: the board flow (what to open on the board and in the console per step, the demo users and their page password, the change request item at T6, D-12 and D-13 and that the drift is a demo device), recovery (resume from a step; fall back to the inbox: `ADLC_BOARD_ENABLED=false` and an API restart, 019), the tokens file; `deploy/README.md` (demo-reset's board part)
- [X] T016 Run `uv run pytest tests/unit tests/integration/engagement tests/integration/demo tests/integration/api tests/contract tests/scenario`, `make ado-sim-check`, ruff and mypy on the changed files; fix anything that fails
- [X] T017 Rehearse (quickstart section 2) as far as this environment allows: with Docker, `make demo-reset` and `make demo-auto` twice and the report checked; without Docker, the auto run in board mode with real processes (the simulator, `adlc-board run`, the driver with stub agents) and the presenter text checked; record what ran, the timings and what remains for a rehearsal with a browser under "Results" in `quickstart.md`

---

## Dependencies and execution order

- Setup (T001–T002) → the change kind (T003–T008) → the board-driven demo (T009–T013) → script steps (T014) → guide, checks, rehearsal (T015–T017).
- Tests first within each task. Parallel: T003–T006 touch different modules; T009 (simulator) with T010–T011; T015 with T016.

## Implementation strategy

MVP: the change kind and the driver in board mode with the existing script (D-1 to D-9 on the board). Then the D-12 and D-13 steps, the guide and the rehearsal.
