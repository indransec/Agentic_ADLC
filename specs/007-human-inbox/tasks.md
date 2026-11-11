# Tasks: Human Inbox

**Input**: Design documents from `specs/007-human-inbox/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Constitution IX makes these test-first:

- inbox rules;
- the decision-form builder;
- error mapping;
- download headers;
- plain-text rendering.

Test tasks come first in each phase and must fail before their implementation.

**Organization**: phases follow the spec's user stories (US1–US3 P1, US4–US5 P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US5)

## Conventions used by every task

- **Where things live:**
  - read-side rules: `src/adlc/inbox/`;
  - HTTP: `src/adlc/api/routes/`;
  - the web application: `src/adlc/ui/`.
- **API tests:** FastAPI's test client over the orchestration harness (template database, stub
  agents and reviewer), signing in with test accounts per role.
- **UI tests:** `streamlit.testing.v1.AppTest`, with an `ApiClient` whose `httpx` transport is an
  ASGI transport to the same app.
- **Text and values:** free text from agents and people is never rendered as Markdown or HTML. No
  terminal ids, role ids or artifact ids appear in `inbox/`, `api/` or `ui/` (constitution I).

---

## Phase 1: Setup

- [X] T001 Add `streamlit==1.66.1` and `python-multipart` to the dependencies, move `httpx` from the dev dependencies to the main ones in `pyproject.toml`, refresh `uv.lock`, and record the licences in the plan.
- [X] T002 Move `deadletter_role`, `synthetic_dir` and `spec_dir` from `OrchestratorSettings` to `RuntimeSettings` in `src/adlc/config/settings.py`, keeping the environment names. Add `UiSettings` with `api_url` (`ADLC_API_URL`, default `http://api:8000`). Tests in `tests/unit/test_settings.py`. Update `.env.example` (`ADLC_API_URL`, `ADLC_UI_PORT=8501`).
- [X] T003 [P] Skeleton:
  - `src/adlc/inbox/__init__.py` and a stub `README.md`;
  - `src/adlc/ui/__init__.py` and `pages/`;
  - `tests/unit/inbox/`, `tests/unit/api/`, `tests/integration/api/` and `tests/integration/ui/`;
  - add `*/adlc/inbox/*` and `*/adlc/api/*` to `CORE_MODULES` in the `Makefile`.
- [X] T004 [P] Compose:
  - a `ui` service (same image, `streamlit run src/adlc/ui/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false`, `ADLC_API_URL=http://api:8000`, port `${ADLC_UI_PORT:-8501}:8501`, healthcheck on `/_stcore/health`, depends on a healthy `api`);
  - the `api` service gets `ADLC_DEADLETTER_ROLE`, `ADLC_SYNTHETIC_DIR` and `ADLC_SPEC_DIR`.

  Done in `deploy/compose.yaml`, with notes in `deploy/README.md`.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T005 [P] Write failing unit tests in `tests/unit/api/test_errors.py` for the error mapping (research R-05):
  - `NotAuthorised` → 403 `not_allowed`;
  - unknown run, use case, waiver, clarification or file → 404 `not_found`;
  - `StaleRun` → 409 `stale`;
  - `InvalidTransition` and `AlreadyAnswered` → 409 `wrong_state`;
  - `InvalidDecision`, `InvalidUpload`, `AttachmentRefused`, `UnknownArtifact` and validation errors → 422 `invalid` (with `field` where known).

  The body is always `{"kind", "detail"}` and never a stack trace.
- [X] T006 [P] Write failing unit tests in `tests/unit/inbox/test_rules.py` for the shared rules `can_sign_off`, `can_answer`, `can_complete_escalation`, `can_decide_waiver`, `can_edit` and `is_coe`:
  - still-needed roles, including required conditional roles;
  - "already approved" excluded;
  - the proposer cannot approve a waiver;
  - editing is allowed only at sign-off or escalation.

### Implementation

- [X] T007 Implement `src/adlc/inbox/rules.py` (T006). Make `OrchestratorService.decide_waiver`, `answer_clarification` and `complete_escalation`, and `LedgerService._editable`, use these rules so the inbox and the operations never disagree. The 003 and 005 suites stay green.
- [X] T008 Add optional `expected_version` to `OrchestratorService.complete_escalation` and to `LedgerService.edit_artifact`, `upload_spreadsheet` and `attach_file`. A mismatch raises `StaleRun`. Tests go in the existing suites.
- [X] T009 Implement `src/adlc/api/errors.py` (T005, exception handlers registered in `create_app`) and `src/adlc/api/deps.py`:
  - the current `Actor` from the session person;
  - the services from `app.state`.

  Make `create_app` build `PostgresTerminalRun` with the real policy engine and stub agent and reviewer, plus `OrchestratorService`, `LedgerService` and `InboxService`. Add the span attributes `account`, `run_id` and `usecase_id`, and never log request bodies. Test in `tests/integration/api/test_tracing.py`: a decision's span carries `account`, `run_id` and `usecase_id`, and no attribute or log line holds the request body (FR-023).

**Checkpoint**: the app starts with all services; errors have one shape.

---

## Phase 3: User Story 1 – Submit a use case and follow it (P1) 🎯 MVP

### Tests first

- [X] T010 [P] [US1] Write failing API tests in `tests/integration/api/test_usecases.py`:
  - `POST /usecases` opens T0 (201 with an id);
  - a person not allowed by T0's rule is refused (403);
  - input limits (422);
  - `GET /usecases?mine=true` lists the submitter's use cases and those where the person holds a role;
  - `GET /usecases/{id}` returns runs, summary and cost;
  - every operation answers 401 without a session (SC-006).
- [X] T011 [P] [US1] Write failing UI tests in `tests/integration/ui/test_intake.py` (AppTest):
  - sign-in, then the intake form submits and shows the new use case's journey with T0;
  - sign-out clears the token;
  - an expired session returns to sign-in.

### Implementation

- [X] T012 [US1] Implement `src/adlc/api/routes/usecases.py` (contracts/api.md: use cases).
- [X] T013 [US1] Implement the UI base and the first page:
  - `src/adlc/ui/client.py`: `ApiClient` (httpx; token; typed errors; injectable through session state);
  - `src/adlc/ui/render.py`: plain-text helpers, tables, error display;
  - `src/adlc/ui/app.py`: sign-in, navigation, sign-out;
  - `src/adlc/ui/pages/intake.py` and `pages/usecases.py`: My use cases or all, and the journey.

**Checkpoint**: a use case can be submitted and followed from the browser.

---

## Phase 4: User Story 2 – Sign off from the inbox with full context (P1)

### Tests first

- [X] T014 [P] [US2] Write failing unit tests in `tests/unit/inbox/test_forms.py` for the decision form built from the pinned specs of T0–T8:
  - the outcomes come from `status_rights.human`;
  - `requires` per outcome (e.g. the exception fields);
  - root causes from the rework routes;
  - typed emitted values;
  - `can_decide` and `can_edit` per person;
  - `reason_required_unless` from the recommendation.
- [X] T015 [P] [US2] Write failing API tests in `tests/integration/api/test_inbox_and_decisions.py`:
  - T1 appears in the inbox of each sign-off role holder only (SC-002), ordered soonest due first;
  - a two-approver rule keeps the run in the second approver's inbox;
  - the run detail has every SA §8.2 field, with prior rework comments newest first;
  - a pass against a rework recommendation without a reason → 422, with one → 200;
  - rework without a comment or root cause → 422, with both → closed and routed;
  - exception creates a pending waiver;
  - a decision with an old version → 409 `stale`, and nothing is recorded (SC-004);
  - a body that names another actor or role (`actor`, `account_name`, `roles`) is refused (422);
    the decision is always recorded under the signed-in person (FR-002).
- [X] T016 [P] [US2] Write failing UI tests in `tests/integration/ui/test_sign_off.py`:
  - the inbox lists the item;
  - the run detail shows each SA §8.2 section;
  - the decision form follows `form` (a reason field appears when the choice differs from the recommendation);
  - a stale answer reloads with a message.

### Implementation

- [X] T017 [US2] Implement `src/adlc/inbox/forms.py` (T014) and `src/adlc/inbox/service.py`:
  - `InboxService.items(actor)` for the sign-off kind, with the ordering of research R-11;
  - `RunDetailService.detail(run_id, actor)` (research R-04, prior rework comments per R-11).
- [X] T018 [US2] Implement `src/adlc/api/routes/inbox.py` and `src/adlc/api/routes/runs.py` (detail, decisions).
- [X] T019 [US2] Implement `src/adlc/ui/pages/inbox.py` (auto-refresh every 30 s and on demand) and `src/adlc/ui/pages/run.py`:
  - every section of SA §8.2, rendered as plain text and tables;
  - the decision form from `form`;
  - version carried on every action.

**Checkpoint**: approvers decide from the inbox.

---

## Phase 5: User Story 3 – Edit artifacts before approving (P1)

### Tests first

- [X] T020 [P] [US3] Write failing API tests in `tests/integration/api/test_artifacts.py`:
  - `PUT` of an edited table creates a person version, resets approvals and shows `controls_pending` until the worker re-checks;
  - an unchanged table → `changed: false`;
  - spreadsheet upload: fitting replaces the rows; not fitting → 422 with the reason;
  - attachment: an allowed file → 200, a disallowed type or one over the size limit → 422;
  - download returns the bytes with the headers of research R-06, and only for attachments of that run;
  - history lists the versions;
  - a person without a sign-off or accountable role → 403;
  - an edit, upload or attachment with an old `expected_version` → 409 `stale`, and no version is
    created (FR-011).
- [X] T021 [P] [US3] Write failing UI tests in `tests/integration/ui/test_artifacts.py`:
  - the data editor saves a change;
  - read-only for non-editors;
  - read-only above 1,000 rows, with upload offered;
  - upload and attach widgets;
  - a download button, never inline content.

### Implementation

- [X] T022 [US3] Implement `src/adlc/api/routes/artifacts.py` (edit, spreadsheet, attachments, history, download).
- [X] T023 [US3] Add the artifact editor, uploads, attachments, downloads and history to `src/adlc/ui/pages/run.py`.

---

## Phase 6: User Story 4 – Clarifications, escalations, waivers, dead letters (P2)

### Tests first

- [X] T024 [P] [US4] Write failing API tests in `tests/integration/api/test_requests.py`:
  - a clarification is listed only for the addressed role, and its answer resumes the same run;
  - an escalation is listed for accountable roles, and completion leads to sign-off (others → 403;
    an old `expected_version` → 409 `stale`);
  - a waiver is listed for approvers other than the proposer, and approval or rejection is recorded with the comment (the proposer → 403);
  - dead letters are listed and requeued only for the CoE role.
- [X] T025 [P] [US4] Write failing UI tests in `tests/integration/ui/test_requests.py` for the clarification, escalation, waiver and dead-letter pages.

### Implementation

- [X] T026 [US4] Extend `InboxService.items` with the clarification, escalation, waiver and dead-letter kinds. Implement the clarification, waiver and dead-letter routes (in one module, `src/adlc/api/routes/requests.py`) and the escalation completion route in `runs.py`.
- [X] T027 [US4] Implement `src/adlc/ui/pages/clarification.py`, `escalation.py`, `waiver.py` and `dead_letters.py`.

---

## Phase 7: User Story 5 – Evidence from the application (P2)

- [X] T028 [P] [US5] Write failing tests in `tests/integration/api/test_evidence.py` and `tests/integration/ui/test_evidence.py`:
  - the timeline, checks, versions and ledger reference are in the run detail;
  - `POST /usecases/{id}/verify` returns the report and records the run under the account.
- [X] T029 [US5] Implement the verify route and the evidence sections in `pages/run.py` and `pages/usecases.py`.

---

## Phase 8: Polish and cross-cutting

- [ ] T030 [P] Rendering-safety test in `tests/integration/ui/test_rendering.py`. Inject `<script>`, HTML and Markdown-link payloads through:
  - the intake;
  - comments;
  - findings (a scripted reviewer);
  - clarification answers;
  - artifact cells.

  Check that no Markdown or HTML element of the rendered pages carries them (research R-07).
- [ ] T031 [P] Extend `tests/unit/test_no_hardcoded_values.py` so `src/adlc/inbox/`, `src/adlc/api/` and `src/adlc/ui/` are covered (terminal, role and route destination ids). Add a boundary test (FR-020): modules in `src/adlc/ui/` import only `adlc.ui` and `adlc.config` from the platform, and never SQLAlchemy, psycopg, `adlc.orchestration`, `adlc.ledger`, `adlc.inbox`, `adlc.agents` or `adlc.db`.
- [ ] T032 [P] Scenario test in `tests/scenario/test_through_the_api.py`: drive the sample lifecycle T0–T8 through the API operations only, with the stub reviewer. Check that:
  - the ledger verifies (SC-005, SC-008);
  - for every terminal, the run detail fetched before the decision has every SA §8.2 field (SC-003).
- [ ] T033 [P] Write `src/adlc/inbox/README.md` and the API section of `src/adlc/api/README.md` (or extend the existing docs): operations, errors, inbox rules and the UI's rendering rules.
- [ ] T034 Run the 003–007 suites 10 times in a row and record the result.
- [ ] T035 Run `make check` and fix any failure, including the 80% core coverage gate that now includes `inbox/` and `api/`.
- [ ] T036 Live check (quickstart §2):
  - run `make up`;
  - open the UI;
  - submit a use case as the business owner from the account file;
  - decide T0 and T1 through the inbox, including one artifact edit and a pass with a reason against the reviewer;
  - verify the ledger.

  Record the result, including the API spans in Jaeger.

---

## Dependencies and execution order

- **Phases:** Phase 1, then Phase 2, then the stories.
- **US1** first: it gives the base UI and client.
- **US2** builds on US1, and **US3** on US2's run detail.
- **US4** and **US5** need Phase 2 and the run detail. They can run in parallel after US2.
- **Phase 8** comes last.

## Parallel examples

- **Phase 2**: T005 and T006 together.
- **US1**: T010 and T011 together.
- **US2**: T014, T015 and T016 together.
- **US3**: T020 and T021 together.
- **US4**: T024 and T025 together.

## Implementation strategy

1. **MVP**: Phases 1–3. Submit and follow a use case.
2. **Sign-off and artifact editing**: Phases 4–5.
3. **Requests and evidence**: Phases 6–7.
4. **Polish**: Phase 8.

Run `make check` and commit at every checkpoint.
