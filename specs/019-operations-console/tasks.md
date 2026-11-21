---

description: "Task list for 019-operations-console"
---

# Tasks: Operations Console

**Input**: Design documents from `specs/019-operations-console/` (spec, plan, research, data-model, contracts, quickstart)

**Prerequisites**: plan.md and spec.md (Gate 1 and Gate 2 approved 2026-11-21)

**Tests**: Requested. Test first for the API routes, the settings and the adapter's `item_url`; web app behaviour through AppTest over the real API (007 research R-08).

**Organization**: by user story (spec US1–US4), after a setup and a foundational phase.

## Format: `[ID] [P?] [Story] Description`

- Paths are relative to the repository root.

---

## Phase 1: Setup

- [X] T001 `deploy/compose.yaml`: define the board settings once (`x-board-settings`) and give them to the `board` and `api` services (research R-02), adding `ADLC_BOARD_PUBLIC_URL: ${ADLC_BOARD_PUBLIC_URL:-http://localhost:8600}`; `.env.example`: `ADLC_BOARD_PUBLIC_URL=` with a comment (the board's address for browsers; defaults to `ADLC_BOARD_URL`); update `tests/unit/test_env_example.py` and any compose test for the new key and the api service's board settings

---

## Phase 2: Foundational

- [X] T002 Settings tests first in `tests/unit/` (the settings test module for `BoardSettings`): `board_public_url` defaults to `board_url`, must be an http(s) address, is not secret; then `BoardSettings.board_public_url` in `src/adlc/config/settings.py` and `ADLC_BOARD_PUBLIC_URL` in the settings documentation table if one is generated
- [X] T003 Adapter tests first (`tests/unit/engagement/`, the ADO adapter's test module and the fake's): `item_url(id)` of the ADO adapter is `{public}/{organization}/{project}/_workitems/edit/{id}` with organisation and project quoted and no double slash; the fake board's is a stable test address; then `BoardAdapter.item_url` in `src/adlc/engagement/port.py`, `src/adlc/engagement/ado.py` (public URL passed from `wiring.build`) and `src/adlc/engagement/fake.py`
- [X] T004 API tests first in `tests/integration/api/test_board_routes.py`: `GET /board/mode` for any signed-in person (`console` with the sync enabled, `inbox` disabled; `board_url` the public address or null; `can_operate` true for the CoE only; 401 signed out); `GET /board/items/{kind}/{object_id}` (a projected use case, run with `/` in its id, clarification; 404 not projected; 422 unknown kind; 404 when disabled); then the two routes in `src/adlc/api/routes/board.py` (read-only, no engagement build needed for `mode`)
- [X] T005 `src/adlc/ui/mode.py`: read `/board/mode` at sign-in and at most every 60 s into the session; keep the last answer on an error (the inbox when none, with a notice); helpers `is_console()`, `board_url()`, `can_operate()`, `item_url(kind, id)` (the API's answer, or None)

---

## Phase 3: User Story 1 – Read the evidence from the board's link (P1) 🎯 MVP

- [X] T006 [P] [US1] AppTest tests in `tests/integration/ui/test_console.py`: with the board enabled (settings in the environment, the engagement on the fake board as in 016's API tests), opening the app at `?run=<id>` signed in opens the Run page on that run; signed out, it opens after sign-in; every evidence section and tab is shown; artifact editing works for the run awaiting the person's sign-off; no decision form; "Decide on the board" links to the run's work item; a run not projected says "not on the board yet"
- [X] T007 [US1] `src/adlc/ui/app.py`: route `?run=` to the Run page (also after the sign-in rerun); `src/adlc/ui/views/run.py`: in console mode replace `decision_form` with the board notice and link (research R-06)

---

## Phase 4: User Story 2 – Watch the sync and reconcile (P1)

- [X] T008 [P] [US2] AppTest tests in `tests/integration/ui/test_sync_status.py`: the CoE sees every health value (ages in human units, refusals by reason), the dead-lettered use cases with "Re-queue" (and the note that this is for board deliveries), the last reconciliation's differences; "Reconcile now" runs only after the confirmation and shows its differences; with the sync disabled the page says so and offers nothing; a person without the role is not offered the page (and the API refuses)
- [X] T009 [US2] `src/adlc/ui/views/sync.py` per research R-07 (refresh at `ADLC_UI_DASHBOARD_REFRESH`; plain text for every value from the platform's tables) and its entry in the Operations section for operators

---

## Phase 5: User Story 3 – A console, not an inbox (P2)

- [X] T010 [P] [US3] AppTest tests in `tests/integration/ui/test_console.py`: in console mode the sidebar lists Use cases, Journey, Activity, Portfolio, Dead letters (and Sync status for the CoE) and the default page is Use cases; Inbox, New use case, Clarification, Escalation and Waiver render the "made on the board" notice with a board link; the SC-002 sweep: every registered page opened in console mode shows no decision radio, no "Submit decision", no intake form, no answer form, no waiver or escalation action
- [X] T011 [US3] `src/adlc/ui/views/moved.py` (the notice) and `src/adlc/ui/app.py` (sidebar sections, default page and page bodies by mode; every page stays registered)

---

## Phase 6: User Story 4 – Switching (P2)

- [X] T012 [P] [US4] Tests: in inbox mode (sync disabled) the web app is as before plus Sync status for the CoE (the existing `tests/integration/ui/` suite passes unchanged, SC-005); the mode is re-read after 60 s (a fake clock in the session); an API error keeps the last mode with a notice; a decision posted to the API in console mode is still accepted (FR-009)

---

## Phase 7: Documentation and the live walk

- [X] T013 [P] Docs: `src/adlc/ui/README.md` (console mode, the pages, the mode's source, the deep link), `deploy/README.md` and `docs/run-without-docker.md` (`ADLC_BOARD_PUBLIC_URL`, the API's board settings, how to fall back to the inbox), `src/adlc/engagement/README.md` (`item_url`)
- [X] T014 Run `uv run pytest tests/unit tests/integration/ui tests/integration/api tests/integration/engagement`, ruff and mypy on the changed files; fix anything that fails
- [X] T015 Walk `specs/019-operations-console/quickstart.md` section 2 live (the API, the web app and the board sync as real processes, as far as the environment allows; the web app driven by AppTest against the live API where a browser is not available): the console's sidebar, the evidence link from a board run item, the removed pages' notices, Sync status with a stopped and restarted simulator and reconcile now, and the inbox back with the sync disabled; record each step under "Results" in `quickstart.md`

---

## Dependencies and execution order

- Setup (T001) → Foundational (T002–T005) → US1 (T006–T007) → US2 (T008–T009) → US3 (T010–T011) → US4 (T012) → Docs and walk (T013–T015).
- Tests first within each story. Parallel: T002 and T003; T006, T008 and T010 (different files).

## Implementation strategy

MVP: the mode answer and US1 (the evidence link to a run with "Decide on the board"). Then Sync status, the console's reduction, the switch's tests, docs and the walk.
