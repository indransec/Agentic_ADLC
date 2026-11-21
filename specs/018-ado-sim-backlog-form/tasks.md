---

description: "Task list for 018-ado-sim-backlog-form"
---

# Tasks: ADO Simulator Backlog and Work Item Form

**Input**: Design documents from `specs/018-ado-sim-backlog-form/` (spec, plan, research, data-model, contracts, quickstart)

**Prerequisites**: plan.md and spec.md (Gate 1 and Gate 2 approved 2026-11-21)

**Tests**: Requested. Test first for the sanitiser, form layout, inputs by type, changed-field diffing, history entries and the backlog tree.

**Organization**: by user story (spec US1–US5), after a setup and a foundational phase.

## Format: `[ID] [P?] [Story] Description`

- Paths are relative to the repository root; the simulator's work is in `ado_sim/` (run its commands from `ado_sim/` with `env -u VIRTUAL_ENV uv run ...`).

---

## Phase 1: Setup

- [X] T001 Record in `ado_sim/contract/differences.md` ("Pages"): comments always shown as plain text (ADO formats them); HTML fields edited as plain text; the backlog shows only the board type's top items and their descendants; the form layout comes from the seed
- [X] T002 Seed data in `ado_sim/seed/demo.yaml`: `Custom.AdlcDecision` in the shared field list with `allowed_values` equal to the decision values of `adlc-specs/tracker_mapping.yaml`; a `form` section per `data-model.md`; regenerate and review the 015 fixtures affected (`work_item_types/*`, `fields/list` if changed); `make ado-sim-check`
- [X] T003 [P] Platform contract test `tests/contract/board/test_decision_values.py`: the seed's allowed values of the decision field equal the tracker mapping's decision values, in the same order (both read as YAML data; no import of `ado_sim`)

---

## Phase 2: Foundational

- [X] T004 Sanitiser tests first in `ado_sim/tests/unit/test_sanitize.py` (each allowed tag kept; attributes dropped except an `http(s)` `href`; `javascript:`, `data:` and relative links removed with their text kept; `script`, `style`, `iframe`, `object`, `template` dropped with their content; text escaped; nested and unclosed tags; a hypothesis property: no output contains `<script`, `on…=` attributes, `javascript:` or `style=`), then `ado_sim/src/ado_sim/pages/sanitize.py` per research R-05 (links get `target="_blank" rel="noopener noreferrer"`)
- [X] T005 Form layout tests first in `ado_sim/tests/unit/test_form_layout.py` (valid layout loads; unknown type, unknown field, a field of another type, a field twice → refusals naming the key; no `form` section is valid), then the seed and storage in `ado_sim/src/ado_sim/seed.py` (`form` key, stored as `form_layout` in `board_setting`) and `process.form_layout(conn)`
- [X] T006 Form model tests first in `ado_sim/tests/unit/test_form.py` (sections from the layout plus "Other fields"; input kind by field type and allowed values per research R-02; read-only system fields; values as text; identity choices exclude the service account; changed fields → patch operations: `test /rev` first, `add` for new values, `remove` for emptied inputs, nothing for unchanged; HTML fields saved escaped in paragraphs; history entries per research R-06 with shortening over 200 characters), then `ado_sim/src/ado_sim/pages/form.py`
- [X] T007 Navigation bar in `ado_sim/src/ado_sim/pages/templates/base.html` (Board, Backlog; `<nav aria-label="Main">`), links built in `routes.py`

---

## Phase 3: User Story 1 – Decide a run from the form (P1) 🎯 MVP

- [X] T008 [P] [US1] Tests first in `ado_sim/tests/pages/test_form_page.py`: each acceptance scenario of spec US1 (the form's sections and inputs; the decision as a list of the seed's values; save attributed to the signed-in user, only changed fields in one update; a conflict keeps the person's values and shows the current item; a refusal beside its field with values kept); escaping of every value; a11y checks of the normal, conflict and error states; retire `ado_sim/tests/pages/test_item.py` (its checks move here)
- [X] T009 [US1] `GET` and `POST /{org}/{project}/_workitems/edit/{id}` in `ado_sim/src/ado_sim/pages/routes.py` with `templates/form.html` (replaces `item.html`): hidden `rev`, CSRF, `WorkItemStore.update` as the signed-in identity, `412` → conflict render, `AdoError` → field error render, `303` back on success
- [X] T010 [US1] The run item's description shown through `sanitize.py` (the only `|safe` use in any template); field values that are wholly `http(s)` addresses shown as links (`target="_blank" rel="noopener noreferrer"`)

---

## Phase 4: User Story 2 – Answer a clarification (P1)

- [X] T011 [P] [US2] Tests in `ado_sim/tests/pages/test_form_page.py`: a clarification item's form shows the questions (formatted) and a multi-line answer field; saving the answer is the person's change in the history

---

## Phase 5: User Story 3 – The backlog tree (P2)

- [X] T012 [P] [US3] Tests first in `ado_sim/tests/unit/test_backlog.py`: roots are the board type's items without a parent (in the area filter); descendants by id at any depth; other parentless items not shown; a cycle in stored links never loops; then `ado_sim/src/ado_sim/pages/backlog.py`
- [X] T013 [P] [US3] Tests first in `ado_sim/tests/pages/test_backlog_page.py`: the page and its fragment, open levels kept on refresh, the filter in the address, escaping, a11y check
- [X] T014 [US3] `GET .../_backlogs/backlog` and `.../_backlogs/backlog/rows` in `routes.py` with `templates/backlog.html` and `rows.html` (nested lists, `<details>` per item with children, polling at the board's interval with `hx-include` of the open set); extend `pages/static/board.js` so opened tree levels travel with the poll as the board's columns do

---

## Phase 6: User Story 4 – Comments, history and the evidence link (P2)

- [X] T015 [P] [US4] Tests in `ado_sim/tests/pages/test_form_page.py`: add a comment (as the person, newest first, plain text); the history with old and new values, shortened long values, link changes; the evidence link opens in a new tab without referrer or opener
- [X] T016 [US4] `POST .../_workitems/edit/{id}/comments` in `routes.py` (`comments.add_comment` as the signed-in identity, `303` to `#comments`); the comments and history sections of `form.html`

---

## Phase 7: User Story 5 – Changing platform-owned fields (P3)

- [X] T017 [P] [US5] Tests in `ado_sim/tests/pages/test_form_page.py`: an Epic's state changed on its form is saved as the person's change (the simulator carries no platform rule); read-only system fields are not editable

---

## Phase 8: Properties

- [X] T018 [P] `ado_sim/tests/properties/test_backlog_timing.py` (SC-002): 200 use cases with two run items and one clarification each (800 items); backlog p95 ≤ 1 s, its fragment ≤ 0.5 s, the form ≤ 0.5 s; printed in the measurements summary
- [X] T019 [P] `ado_sim/tests/properties/test_concurrent_saves.py` (SC-003): two sessions open the same form and save different changes; for every pair, the second gets the conflict with its values kept; no silent overwrite
- [X] T020 [P] `ado_sim/tests/properties/test_hostile_values.py` (SC-004): hostile titles, descriptions, comments, answers and field values on the board, the backlog and the form: never rendered as markup or executable

---

## Phase 9: Documentation and the live walk

- [X] T021 [P] `ado_sim/README.md` ("Pages": the form, the backlog, the form layout and the decision list in the seed) and `docs/run-without-docker.md` (the backlog address)
- [X] T022 Run `make ado-sim-check`, `uv run pytest tests/contract/board tests/unit/test_env_example.py` (platform) and `ado-sim export-openapi --check`; fix anything that fails
- [X] T023 Walk `specs/018-ado-sim-backlog-form/quickstart.md` section 2 live with 016's sync running (the simulator and `adlc-board run` as real processes, the platform's orchestrator with stub agents as in 016's walk; people act through the pages over HTTP with sessions and CSRF): registration from the board, the backlog tree, a sign-off from the form, an Epic's state changed and set back, a conflict; record each step under "Results" in `quickstart.md` (SC-006)

---

## Dependencies and execution order

- Setup (T001–T003) → Foundational (T004–T007) → US1 (T008–T010) → US2 (T011) → US3 (T012–T014) and US4 (T015–T016) → US5 (T017) → Properties (T018–T020) → Docs and walk (T021–T023).
- Tests first within each story. Parallel: T003 with T001–T002; T012–T013 with T015; T018–T020.

## Implementation strategy

MVP: US1 (the form with the decision). Then the clarification answer, the backlog, comments and history, the US5 checks, properties, and the live walk with the platform.
