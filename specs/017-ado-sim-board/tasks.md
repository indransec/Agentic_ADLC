---

description: "Task list for 017-ado-sim-board"
---

# Tasks: ADO Simulator Board

**Input**: Design documents from `specs/017-ado-sim-board/` (spec, plan, research, data-model, contracts, quickstart)

**Prerequisites**: plan.md and spec.md (Gate 1 and Gate 2 approved 2026-11-21)

**Tests**: Requested. Core modules are test first (constitution IX): credential checks and hashing, sessions and CSRF, seed board settings, board grouping.

**Organization**: by user story (spec US1–US5), after a setup and a foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to
- Paths are relative to the repository root; everything is in the simulator's own project `ado_sim/` (run its commands from `ado_sim/` with `env -u VIRTUAL_ENV uv run ...`)

---

## Phase 1: Setup

- [X] T001 Compare the page addresses with real Azure DevOps (board `https://dev.azure.com/{org}/{project}/_boards/board/t/{team}/{backlog level}`, item `.../_workitems/edit/{id}`) and the link 015 writes (`_links.html` in `ado_sim/src/ado_sim/render.py`); record in `ado_sim/contract/differences.md` under a new "Pages" heading every difference (no team or backlog-level segment, `/_signin` instead of Microsoft sign-in, the read-only item page until 018)
- [X] T002 Add `jinja2==3.1.6` and `python-multipart==0.0.32` to `ado_sim/pyproject.toml` dependencies (same versions as the platform's `uv.lock`), run `cd ado_sim && uv lock`, record both with their licences (BSD-3-Clause, Apache-2.0) in `ado_sim/README.md` ("Dependencies")
- [X] T003 [P] Vendor HTMX 2.0.4 as `ado_sim/src/ado_sim/pages/static/htmx.min.js` from `https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js`, with its licence text as `ado_sim/src/ado_sim/pages/static/HTMX-LICENSE` (0BSD); record the source URL and SHA-256 in `ado_sim/src/ado_sim/pages/static/README.md`; make sure the package data (templates, static) is included in the wheel (`[tool.hatch.build]` in `ado_sim/pyproject.toml`)
- [X] T004 [P] Extend `ado_sim/tests/test_boundary.py`: templates and static files hold no `adlc` import, no `ADLC_` string and no reference to an external host (no `http://`/`https://` other than the vendored files' licence comments)

---

## Phase 2: Foundational

- [X] T005 Write `ado_sim/src/ado_sim/migrations/0002_pages.sql` exactly as `data-model.md`: `page_password (identity_id TEXT PRIMARY KEY REFERENCES identity(id), password_hash TEXT NOT NULL, set_at TEXT NOT NULL)` and `page_session (session_hash TEXT PRIMARY KEY, identity_id TEXT NOT NULL REFERENCES identity(id), csrf_token TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT NULL)` with an index on `identity_id`; `board_setting (key TEXT PRIMARY KEY, value TEXT NOT NULL)` (JSON values) and `ALTER TABLE identity ADD COLUMN is_service INTEGER NOT NULL DEFAULT 0`; test in `ado_sim/tests/unit/test_schema.py` (migration 2 applied, idempotent)
- [X] T006 Settings first in `ado_sim/tests/unit/test_settings.py`, then `ado_sim/src/ado_sim/settings.py`: `ADO_SIM_PAGE_SESSION_TTL` (default `8h`, the 015 duration form), `ADO_SIM_DEMO_PASSWORD` (optional, at least 12 characters, `repr=False`, never in errors), `ADO_SIM_SECURE_COOKIES` (bool, default false)
- [X] T007 Seed tests first in `ado_sim/tests/unit/test_board_settings.py`, then `ado_sim/src/ado_sim/seed.py`: the optional `board` section (`type` an existing type; `card_fields` fields of that type; `collapsed_states` states of that type; `refresh` `<int>s` between 2 and 60) and `service: true` on at most one identity, each refusal naming the key; store them in `board_setting` and `identity.is_service` (T005); `process.py` gains `board_settings(conn)` and `is_service(identity)`; update `ado_sim/seed/demo.yaml` (`service: true` on `adlc-platform@adlc.demo`; `board: {type: Epic, card_fields: [Custom.AdlcSubStage], collapsed_states: [Closed, Removed], refresh: 5s}`)
- [X] T008 Credential tests first in `ado_sim/tests/unit/test_signin.py` (page password hash and verify, `scrypt$` format; the demo password only when set; a valid token of that user, not of another; the service account always refused; unknown user refused; every failure the same message and a comparable amount of work, the dummy scrypt), then `ado_sim/src/ado_sim/pages/signin.py`
- [X] T009 Session tests first in `ado_sim/tests/unit/test_sessions.py` (create returns a random id and stores only its SHA-256; read by id; expired → none; revoked → none; `revoke_all(identity)`; CSRF token per session, constant-time check; housekeeping removes expired and revoked rows), then `ado_sim/src/ado_sim/pages/sessions.py`
- [X] T010 Wire `revoke_all` into `ado-sim token revoke` (`ado_sim/src/ado_sim/auth.py` or `cli.py`) so revoking a token ends that user's page sessions (FR-004a); test in `ado_sim/tests/unit/test_cli.py`
- [X] T011 `ado-sim password set <unique-name> [--stdin] | --all` and `password clear <unique-name>` in `ado_sim/src/ado_sim/cli.py` per `contracts/cli-settings-seed.md` (no echo, typed twice, at least 12 characters; `clear` ends the user's sessions; exit codes 0, 1, 2); tests in `ado_sim/tests/unit/test_cli.py`
- [X] T012 The page gate in `ado_sim/src/ado_sim/app.py`: paths under `/_apis/` keep token auth (unchanged); `/health`, `/openapi.json`, `/_signin`, `/_static/*` public; every other path needs a page session (full page → `303 /_signin?next=`; HTMX request → `200` with `HX-Redirect: /_signin`); POSTs check CSRF (`403`); page responses get the security headers of `contracts/pages.md`; page requests are logged like API requests (operation, identity, status, duration; never form values or cookies); page routes registered with `include_in_schema=False`; `ado-sim export-openapi --check` still passes unchanged
- [X] T013 Templates base and error pages: `ado_sim/src/ado_sim/pages/templates/base.html` (`<html lang="en">`, header landmark with the signed-in user and a sign-out form, `<main>`, `hx-headers` with the CSRF token on `<body>`, the stylesheet and HTMX from `/_static/`), `error.html` (404, 400), Jinja2 environment with autoescape on for every template in `ado_sim/src/ado_sim/pages/__init__.py`; `ado_sim/src/ado_sim/pages/static/board.css` (columns layout, visible focus styles, no horizontal page scroll at 1280×720)
- [X] T014 Write the static accessibility checker `ado_sim/tests/pages/a11y.py` (research R-09: `lang`, one `main`, `header` and `nav` landmarks, one `h1`, labels for every input, names for every button and link, no positive `tabindex`) and the test fixtures in `ado_sim/tests/pages/conftest.py` (a test client, a signed-in client per demo user via a page password, the CSRF token helper)

**Checkpoint**: sessions, credentials, settings, seed and the page gate work; stories can start.

---

## Phase 3: User Story 1 – Sign in as a demo user (P1) 🎯 MVP

- [X] T015 [P] [US1] Tests first in `ado_sim/tests/pages/test_signin.py`: each acceptance scenario of spec US1 (the list without the service account; each of the three credentials; one refusal message; sign-out ends the session; an expired session; `next` accepted only as a local path; the sign-in form's pre-session CSRF); a11y check of the page
- [X] T016 [US1] `GET/POST /_signin` and `POST /_signout` in `ado_sim/src/ado_sim/pages/routes.py` with `ado_sim/src/ado_sim/pages/templates/signin.html`; the session cookie per research R-02 (`HttpOnly`, `SameSite=Lax`, `Secure` when `ADO_SIM_SECURE_COOKIES`); a warning logged at start when `ADO_SIM_DEMO_PASSWORD` is set
- [X] T017 [US1] `ado_sim/tests/pages/test_access.py`: a sweep of every page route (from the app's routes, not a hand list) without a session → redirect or `HX-Redirect`; every page POST without CSRF → 403; API routes still answer 401 without a token (SC-004)

---

## Phase 4: User Story 2 – See every Epic in its column (P1)

- [X] T018 [P] [US2] Tests first in `ado_sim/tests/unit/test_board.py`: columns in the process's order from the board settings; one card per item of the board type; cards by id; collapsed states; an "other" column for states the type no longer lists; card fields and last changer; an empty sub-stage shows nothing
- [X] T019 [US2] `ado_sim/src/ado_sim/pages/board.py`: `columns(conn, area)` per research R-06 (one read transaction; the board type, area and below)
- [X] T020 [P] [US2] Tests first in `ado_sim/tests/pages/test_board_pages.py`: the board page and its fragment for a signed-in user; markup in titles and card fields shown escaped; no control to move a card between columns and no drag-and-drop attribute (FR-007); a11y check; 200 Epics render
- [X] T021 [US2] `GET /{org}/{project}/_boards/board` and `.../cards` in `ado_sim/src/ado_sim/pages/routes.py`, templates `board.html` and `columns.html` (`<h2>` per column with its count, `<details>` for collapsed columns, each card a link to the item page)
- [X] T022 [P] [US2] Tests first in `ado_sim/tests/pages/test_item.py`: the read-only item page (fields as text, parent and children, updates with who and when, comments); unknown id → 404 page; a11y check
- [X] T023 [US2] `GET /{org}/{project}/_workitems/edit/{id}` with `item.html` in `ado_sim/src/ado_sim/pages/routes.py`, reading through `WorkItemStore.get`, `updates` and `comments.list_comments`

---

## Phase 5: User Story 3 – The board keeps up with the platform (P1)

- [X] T024 [P] [US3] Tests first in `ado_sim/tests/pages/test_refresh.py`: the fragment reflects an API change made between two polls; open `<details>` states sent with the poll come back open; an expired session gives `HX-Redirect`; the board page carries the polling attributes with the seed's interval and the error banner hooks
- [X] T025 [US3] Polling in `board.html` and `columns.html` per research R-07 (`hx-get` the fragment `every <refresh>s`, `hx-include` of open columns, the "not current" banner on HTMX error events and cleared on success, no live region)

---

## Phase 6: User Story 4 – Create an Epic from the board (P2)

- [X] T026 [P] [US4] Tests first in `ado_sim/tests/pages/test_create.py`: create as the signed-in user (history shows them, SC-003); a missing title or an unknown area → the form with the simulator's message beside the field and values kept, 400; only existing areas offered, defaulting to the filter; CSRF required
- [X] T027 [US4] `POST /{org}/{project}/_boards/board/epics` and the create form in `board.html`, calling `WorkItemStore.create` with the board type and the signed-in identity

---

## Phase 7: User Story 5 – Filter by area path (P2)

- [X] T028 [P] [US5] Tests first in `ado_sim/tests/pages/test_filter.py`: area and below; counts follow; the filter is in the address and kept by the fragment; an unknown area → the board unfiltered with a notice
- [X] T029 [US5] The area filter (a `<form method="get">` with a labelled select of the area tree) in `board.html` and the `area` parameter in `routes.py`

---

## Phase 8: Properties

- [X] T030 [P] `ado_sim/tests/properties/test_board_timing.py` (SC-001): 200 Epics; p95 of the board page ≤ 1 s and of the fragment ≤ 0.5 s, printed in the measurements summary
- [X] T031 [P] `ado_sim/tests/properties/test_board_changes.py` (SC-002): 50 state and sub-stage changes through the API, each visible in the next fragment
- [X] T032 [P] `ado_sim/tests/properties/test_no_secrets_in_page_logs.py` (SC-004): sign in with each credential kind, fail with wrong ones, create, sign out; no password, token, session id, CSRF token or form value in any captured log line
- [X] T033 [P] Extend `ado_sim/tests/properties/test_no_tokens.py`: the page tables hold no token or password in clear (only hashes)

---

## Phase 9: Deployment and documentation

- [X] T034 [P] `deploy/compose.yaml` and `.env.example`: pass `ADO_SIM_DEMO_PASSWORD` (empty by default) and `ADO_SIM_PAGE_SESSION_TTL` to the `ado-sim` service; `tests/unit/test_env_example.py` treats `ADO_SIM_DEMO_PASSWORD` as a compose-only secret that must be empty
- [X] T035 [P] `ado_sim/README.md` ("Pages": sign-in, the three credentials, `ado-sim password`, the board, settings), `deploy/README.md` (setting demo passwords in the container) and `docs/run-without-docker.md` (opening the board on 8600)
- [X] T036 Run `make ado-sim-check`, `uv run pytest tests/unit` (platform: env example, boundaries) and `cd ado_sim && uv run ado-sim export-openapi --check`; fix anything that fails
- [X] T037 Walk `specs/017-ado-sim-board/quickstart.md` section 3 live (the simulator's own process on a scratch database and port, sign-in through HTTP with a real session cookie, the fragment after an API change, the create form with CSRF) and record each step's status and result under "Results" in `specs/017-ado-sim-board/quickstart.md`

---

## Dependencies and execution order

- Setup (T001–T004) → Foundational (T005–T014) → US1 (T015–T017) → US2 (T018–T023) → US3 (T024–T025); US4 (T026–T027) and US5 (T028–T029) after US2 → Properties (T030–T033) → Deployment and docs (T034–T037).
- Within a story: tests first, then the implementation.
- Parallel: T003 and T004; T006 with T005; T015 with T018 once Phase 2 is done; T030–T033; T034–T035.

## Implementation strategy

MVP: Phases 1–4 (sign-in and the board). Then refresh (the demo needs it), create, filter, properties, deployment and the live walk.
