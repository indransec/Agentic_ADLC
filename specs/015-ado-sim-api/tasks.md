---

description: "Task list for 015-ado-sim-api"
---

# Tasks: ADO Simulator API

**Input**: Design documents from `specs/015-ado-sim-api/` (spec, plan, research, data-model, contracts, quickstart)

**Prerequisites**: plan.md and spec.md (Gate 1 and Gate 2 approved 2026-11-20)

**Tests**: Requested. Core modules are test first (constitution IX): write the unit tests for patch, WIQL, history, relations, auth and seed, see them fail, then implement.

**Organization**: by user story (spec US1–US8), after a setup and a foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to
- Paths are relative to the repository root; the simulator lives in `ado_sim/` (its own uv project)

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: the `ado_sim/` project, the reference check and both import boundaries.

- [X] T001 Confirm every operation in `specs/015-ado-sim-api/contracts/operations.md` against its Microsoft Learn 7.1 reference page (`https://learn.microsoft.com/rest/api/azure/devops/<area>/<page>?view=azure-devops-rest-7.1`): method, path, query parameters, body and response shape, and api-version (comments `7.1-preview.4`); record the full URL per operation in a "Reference" column; establish from the comments reference whether adding a comment creates a new work item revision and changes `System.ChangedDate` (record the answer in `contracts/operations.md` and T033 follows it); note any correction in `ado_sim/contract/differences.md` (create it with a header and the differences already known from research R-02)
- [X] T002 Create the uv project `ado_sim/` mirroring `pilot/`: `ado_sim/pyproject.toml` (name `adlc-ado-sim`, Python `>=3.12,<3.13`, dependencies fastapi 0.162.2, uvicorn 0.54.0, pydantic 2.14.3, ruamel-yaml 0.19.1, opentelemetry-api/-sdk/-exporter-otlp-proto-http 1.45.2, coverage, bandit as in `pilot/pyproject.toml`; dev group mypy, pytest, pytest-cov, ruff, httpx 0.28.1; script `ado-sim = "ado_sim.cli:main"`; hatch packages `src/ado_sim`; ruff line length 100 with the pilot's rule set; mypy strict), `ado_sim/src/ado_sim/__init__.py`, `ado_sim/tests/__init__.py`, `ado_sim/README.md` (stub), then `cd ado_sim && uv lock`
- [X] T003 [P] Write `ado_sim/tests/test_boundary.py`: no module under `ado_sim/src` imports `adlc` (parse every file's imports with `ast`), and the seed file and package hold no `ADLC_` string (SC-008, FR-023)
- [X] T004 [P] Write `tests/unit/test_ado_sim_boundary.py` in the platform: no module under `src/adlc` imports `ado_sim` (SC-008)
- [X] T005 [P] Add `ado_sim/.gitignore` entries if needed and confirm the root `.gitignore` covers `ado_sim/.venv/` and `data/local/` (both patterns already exist; add only what is missing)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: settings, database, migrations, process and seed loading, errors, auth and the app shell. No user story can start before this phase is done.

- [X] T006 Write `ado_sim/src/ado_sim/settings.py`: frozen dataclass loaded from the environment (`ADO_SIM_DB_PATH` required; `ADO_SIM_TOKEN_KEY` required with at least 32 characters; `ADO_SIM_PORT` 8600; `ADO_SIM_SEED_FILE` `seed/demo.yaml`; `ADO_SIM_BUSY_TIMEOUT` `30s` in the `<int><unit>` form; `ADO_SIM_LOG_LEVEL` INFO; `ADO_SIM_OTLP_ENDPOINT` optional); a missing or invalid value raises an error naming the variable and the expected form, never the value; unit tests in `ado_sim/tests/unit/test_settings.py`
- [X] T007 Write `ado_sim/src/ado_sim/db.py`: open the SQLite file (`mode=rw` for serving, `rwc` for migrate), set WAL, `foreign_keys=ON`, busy timeout; `write()` context manager that runs `BEGIN IMMEDIATE` and commits or rolls back; `read()` that uses a plain `BEGIN`; `utc_now()` returning ISO 8601 UTC text with microseconds (`2026-11-20T10:15:30.123456Z`); a migrations runner that applies `src/ado_sim/migrations/NNNN_*.sql` in order and records `schema_version`; unit tests in `ado_sim/tests/unit/test_db.py` (WAL on, write lock serialises two writers, migrations idempotent)
- [X] T008 Write `ado_sim/src/ado_sim/migrations/0001_initial.sql` exactly as `data-model.md`: tables `organization`, `project`, `area_node`, `work_item_type`, `work_item_type_state`, `field`, `work_item_type_field`, `identity`, `access_token` (`token_hash` unique, `revoked_at` null while valid), `work_item` (indexes on `changed_date`, `state`, `area_path`, `type_name`), `revision` (PK `work_item_id`, `rev`), `work_item_update` (PK `work_item_id`, `rev`), `relation` (PK `source_id`, `target_id`, `rel`), `comment`; triggers refusing UPDATE and DELETE on `revision` and `work_item_update` ("append-only"); test the triggers in `ado_sim/tests/unit/test_schema.py`
- [X] T009 Write the seed tests first in `ado_sim/tests/unit/test_seed.py`: a valid file loads organisation, project, area tree, types with states and categories, fields with types, type-field assignments and identities; refusals for an unknown field type, a type without states, a duplicate unique name, an area path outside the project, a state category outside `Proposed, InProgress, Resolved, Completed, Removed`, and any key named like a token or secret
- [X] T010 Write `ado_sim/src/ado_sim/seed.py` (ruamel.yaml): validate and load a seed file into an empty database inside one write transaction (refuse if any work item exists); the format is `contracts/cli-settings-seed.md` ("Seed file"), with `states: agile` expanding to `agile_states`
- [X] T011 Write `ado_sim/seed/demo.yaml`: organisation `adlc-demo`, project `Agentic ADLC`, areas `Use cases`; Agile process with the Epic's states as the ten terminal stages plus `Closed` and `Removed` (stage names as data only), Feature, User Story, Task, Bug with the Agile states; custom fields `Custom.AdlcUseCaseId`, `Custom.AdlcSubStage`, `Custom.AdlcRunId`, `Custom.AdlcDecision`, `Custom.AdlcComment`, `Custom.AdlcClarificationAnswer`; identities `adlc-platform@adlc.demo` (service account) and one demo user per platform role used in the demo (business owner, product owner, engineering lead, QA lead, risk officer, release manager, SRE, CoE lead); no tokens
- [X] T012 Write `ado_sim/src/ado_sim/errors.py`: `AdoError(status, message, type_name, type_key)` and the ADO error body (`$id`, `innerException`, `message`, `typeName`, `typeKey`, `errorCode`, `eventId`); mapping for 400 invalid, 404 not found, 412 failed test, 401 with an empty body (FR-015); unit tests in `ado_sim/tests/unit/test_errors.py`
- [X] T013 Write the auth tests first in `ado_sim/tests/unit/test_auth.py`: tokens are 52 characters from `secrets`; the stored hash is HMAC-SHA256 with `ADO_SIM_TOKEN_KEY`; Basic auth (any user, token as password) and Bearer both authenticate; missing, malformed, unknown, revoked and wrong tokens all give the same 401 with an empty body; comparison is constant time; a changed key invalidates every token
- [X] T014 Write `ado_sim/src/ado_sim/auth.py`: issue (returns the token once), revoke, list (never tokens), authenticate a request header to an active identity
- [X] T015 Write `ado_sim/src/ado_sim/cli.py` with `migrate`, `seed --file [--if-new]`, `token issue <unique-name> [--label]`, `token revoke <id>`, `token list [<unique-name>]` and their exit codes from `contracts/cli-settings-seed.md` (0, 1 refused, 2 settings or invalid file); `ado_sim/src/ado_sim/__main__.py` calls `cli.main`; CLI tests in `ado_sim/tests/unit/test_cli.py`
- [X] T016 Write `ado_sim/src/ado_sim/app.py` shell: FastAPI app factory taking settings; middleware that authenticates every request except `GET /health` and `GET /openapi.json`; `api-version` check (FR-025: missing or unsupported → 400 naming the supported versions); request size limits (FR-026: body over 5 MB → 400); ADO error handlers; `GET /health`; and `ado_sim/src/ado_sim/observability.py` with one log line per request (operation, identity unique name, status, duration; never field values, comment text or tokens) and optional OTLP traces when `ADO_SIM_OTLP_ENDPOINT` is set
- [X] T017 Write `ado_sim/tests/conftest.py`: fixtures for a migrated and seeded temporary database, settings with a test key, a FastAPI `TestClient`, and issued tokens for the service account and two demo users

**Checkpoint**: settings, database, seed, tokens and the authenticated app shell work; user stories can start.

---

## Phase 3: User Story 1 – Create, read and update work items (P1) 🎯 MVP

**Goal**: create, get, list, batch and update work items with ADO JSON Patch and `test /rev`.

**Independent Test**: spec US1: create, read, patch two fields, read revision 2, stale `test /rev` refused with 412 and the item unchanged.

### Tests for User Story 1 (write first, see them fail)

- [X] T018 [P] [US1] Write `ado_sim/tests/unit/test_patch.py`: `add`, `replace`, `remove`, `test` on `/fields/<ref>`; `test` on `/rev`; `/relations/-` add and `/relations/<i>` remove (relation semantics are US4, here only parsing); all-or-nothing on any invalid operation; unknown field for the type and a state not allowed for the type refused (FR-005); read-only system fields refused; more than 500 operations refused (FR-026); a patch with no effective change returns "no change"
- [X] T019 [P] [US1] Write `ado_sim/tests/api/test_work_items.py` covering spec US1 scenarios 1–6: create with system fields (`System.Id`, `System.Rev` 1, `System.State` the type's first state, `System.AreaPath` default the project root, `System.CreatedBy`/`ChangedBy` the caller, dates); get with `fields`, `asOf`, `$expand`; list `?ids=` in order, more than 200 ids → 400, `errorPolicy` `Fail` → 404 for a missing id, `Omit` → left out (FR-002); batch `POST workitemsbatch` same rules; update with `test /rev` success and 412 conflict leaving the item unchanged; the Epic moved to the next terminal stage with `Custom.AdlcSubStage`; a field value over 1 MB → 400

### Implementation for User Story 1

- [X] T020 [US1] Implement `ado_sim/src/ado_sim/patch.py`: parse ADO JSON Patch into field changes, relation changes and an expected revision; validate against the item's type (fields, allowed states, read-only fields) without touching the database
- [X] T021 [US1] Implement `ado_sim/src/ado_sim/workitems.py` (part 1): `create`, `get`, `get_many`, `update` inside one write transaction each: allocate ids from 1 upward, set system fields, apply the patch, bump `rev` by exactly one, set `System.ChangedDate` strictly later than the previous one (previous + 1 µs on a tie, research R-06), write `work_item`, one `revision` row (full fields and relations) and one `work_item_update` row (old and new values, changer, time); no new revision for a patch with no effective change; identity fields returned as ADO identity references
- [X] T022 [US1] Add the work item routes to `ado_sim/src/ado_sim/app.py`: `POST /{organization}/{project}/_apis/wit/workitems/${type}`, `GET .../workitems/{id}`, `GET .../workitems?ids=`, `POST .../workitemsbatch`, `PATCH .../workitems/{id}` (content type `application/json-patch+json`; `validateOnly` validates without saving; `bypassRules` refused with 400), responses shaped as ADO (`id`, `rev`, `fields`, `relations` when expanded, `_links`, `url`)

**Checkpoint**: User Story 1 works on its own.

---

## Phase 4: User Story 2 – Read every change, in order, with who made it (P1)

**Goal**: updates and revisions, complete and ordered, attributed.

**Independent Test**: spec US2: three changes by two users between two reads, all returned in order with old and new values and the right changer.

- [X] T023 [P] [US2] Write `ado_sim/tests/unit/test_history.py` first: one update per change with `rev`, old and new values (no `oldValue` on creation), relation changes, `revisedBy`, `revisedDate`; revisions reproduce the item exactly; changed dates strictly increase per item even when the clock repeats a value; update and revision rows cannot be changed
- [X] T024 [P] [US2] Write `ado_sim/tests/api/test_history.py`: spec US2 scenarios 1–4 through `GET .../workItems/{id}/updates` (`$top`, `$skip`), `GET .../updates/{n}`, `GET .../revisions` and `GET .../revisions/{n}`
- [X] T025 [US2] Implement the history reads in `ado_sim/src/ado_sim/workitems.py` (part 2) and their routes in `ado_sim/src/ado_sim/app.py`, shaped as `contracts/operations.md` ("History")

---

## Phase 5: User Story 3 – Query work items (WIQL subset) (P1)

**Goal**: the documented WIQL subset; everything else refused by name.

**Independent Test**: spec US3: each supported form returns exactly the expected ids in order; `EVER` refused naming `EVER`.

- [X] T026 [P] [US3] Write `ado_sim/tests/unit/test_wiql.py` first: tokenizer (brackets, quoted strings with escaped quotes, numbers, dates, `@project`, `@today - n`); parser for flat queries (`=`, `<>`, `<`, `<=`, `>`, `>=`, `IN`, `UNDER`, `AND`, `OR`, `NOT`, parentheses, `ORDER BY ... ASC|DESC`) and link queries (`FROM workitemLinks`, `[Source].`, `[Target].`, `[System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'`, `MODE (MustContain)`); refusal naming each construct in `contracts/wiql.md` "Refused" and any field not in the process; queries over 32 KB refused (FR-026)
- [X] T027 [P] [US3] Write `ado_sim/tests/api/test_wiql.py`: spec US3 scenarios 1–3; `ChangedDate >= <latest seen>` with microsecond precision returns the item changed in that instant (research R-06); `$top` limit, more than 20,000 refused; link query result shape (`workItemRelations` with a `source: null` row per source, then one per link)
- [X] T028 [US3] Implement `ado_sim/src/ado_sim/wiql.py`: tokenizer, recursive-descent parser and compiler to parameterised SQL over `work_item` (JSON field extraction for non-indexed fields), with `UNDER` matching the area path and its descendants
- [X] T029 [US3] Add `POST /{organization}/{project}/_apis/wit/wiql` to `ado_sim/src/ado_sim/app.py`, answering flat (`workItems`) and one-hop (`workItemRelations`) results as `contracts/operations.md` ("Queries")

---

## Phase 6: User Story 4 – Link work items (P2)

**Goal**: hierarchy and dependency links, atomic on both items.

**Independent Test**: spec US4: link, read with relations, remove; second parent, cycle and self-link refused.

- [X] T030 [P] [US4] Write `ado_sim/tests/unit/test_relations.py` first: adding a child link adds the parent link on the target (and dependency forward/reverse likewise); both items get one new revision and update in one transaction (FR-012), or neither on refusal; second parent, cycle (walk the parent chain), self-link and missing target refused (FR-013); removing by `/relations/<index>` removes both directions
- [X] T031 [P] [US4] Write `ado_sim/tests/api/test_relations.py`: spec US4 scenarios 1–3 through the update and get routes with `$expand=Relations`
- [X] T032 [US4] Implement relation handling in `ado_sim/src/ado_sim/workitems.py` (part 3): apply relation changes from a patch to both items inside the same write transaction, record them in both items' updates and revisions

---

## Phase 7: User Story 5 – Comment on work items (P2)

**Goal**: add and list comments with author and time.

**Independent Test**: spec US5: three comments by two users listed in both orders with authors.

- [X] T033 [P] [US5] Write `ado_sim/tests/api/test_comments.py`: add (`7.1-preview.4`), list with `order` asc and desc, `$top` (max 200) and `continuationToken` paging, author and time, the item's `System.CommentCount` increases, and the revision behaviour T001 established (new revision or not) holds; comment text over 1 MB → 400
- [X] T034 [US5] Implement `ado_sim/src/ado_sim/comments.py` and its routes in `ado_sim/src/ado_sim/app.py`

---

## Phase 8: User Story 6 – Identities and access (P2)

**Goal**: identities readable; every change attributed; tokens issued and revoked by command.

**Independent Test**: spec US6: no, wrong, revoked and valid tokens; only the valid one answered; the change names its identity; lookup by unique name.

- [X] T035 [P] [US6] Write `ado_sim/tests/api/test_identities.py`: spec US6 scenarios 1–4; `GET /{organization}/_apis/identities?searchFilter=General&filterValue=<unique-name>` and `?identityIds=` shaped as `contracts/operations.md`; the 401 for every bad token is identical and empty; a token revoked by the CLI is refused on the next request
- [X] T036 [US6] Implement `ado_sim/src/ado_sim/process.py` (identities part) and the identities route in `ado_sim/src/ado_sim/app.py`

---

## Phase 9: User Story 7 – Seeded organisation, project, area paths and process (P2)

**Goal**: process and area reads, reset and restart.

**Independent Test**: spec US7: reset from the seed, read areas, types with states and identities; data before the reset gone; data survives a restart.

- [X] T037 [P] [US7] Write `ado_sim/tests/api/test_process.py`: `GET .../workitemtypes`, `.../workitemtypes/{type}`, `.../workitemtypes/{type}/states`, `.../fields`, `.../classificationnodes/Areas?$depth=` match the seed file
- [X] T038 [P] [US7] Write `ado_sim/tests/unit/test_reset_restart.py`: `reset` without `--yes` refused; with `--yes` drops and recreates every table and seeds from `ADO_SIM_SEED_FILE`; closing and reopening the database keeps every work item, revision, update, relation and comment (SC-005)
- [X] T039 [US7] Implement the process and area reads in `ado_sim/src/ado_sim/process.py` with their routes, and `reset --yes` in `ado_sim/src/ado_sim/cli.py` (the only path that removes append-only rows: drop and recreate the tables, then seed)

---

## Phase 10: User Story 8 – A published contract with fixtures (P2)

**Goal**: the committed OpenAPI document, fixtures for every operation and refusal, the differences list.

**Independent Test**: spec US8: every fixture passes against a freshly seeded simulator; the served document equals the committed one and lists exactly the served operations.

- [X] T040 [US8] Add `ado-sim export-openapi [--check]` to `ado_sim/src/ado_sim/cli.py`; make every route declare its parameters, request body and responses (including refusals) so the generated document is complete; serve `GET /openapi.json` unauthenticated; commit `ado_sim/contract/openapi.json`
- [X] T041 [US8] Write the fixtures under `ado_sim/contract/fixtures/<operation>/<case>.json` (request: method, path, query, body; expected: status and a body pattern where ids and times are matched by type): one success case per operation in `contracts/operations.md`, plus `update/stale_rev` (412), `update/unknown_field` (400), `get/unknown_item` (404), `list/too_many_ids` (400), `wiql/unsupported_ever` (400), `any/no_token` (401), `any/missing_api_version` (400), `any/unsupported_operation` (404), `any/unknown_project` (404); no token in any fixture
- [X] T042 [US8] Write `ado_sim/tests/contract/test_fixtures.py` (replay every fixture against a freshly seeded app with a test token, SC-001) and `ado_sim/tests/contract/test_openapi.py` (served document equals `contract/openapi.json`; its paths equal the app's routes; any other `/_apis/` path → 404, FR-020)
- [X] T043 [US8] Complete `ado_sim/contract/differences.md`: identities on the simulator's host, no revision limit, `bypassRules` refused, `/health` and `/openapi.json`, statuses not stated by the reference (412 and the others in research R-02), each with the reason and "to confirm against real ADO before a real tracker is connected"

---

## Phase 11: Properties (success criteria across stories)

- [X] T044 [P] Write `ado_sim/tests/properties/test_polling_completeness.py` (SC-002): 1,000 changes to 50 items by four identities in a background thread while a reader polls every 50 ms with `ChangedDate >= <latest seen>` and reads updates; the reader sees every update exactly once (de-duplicated by id and rev), in revision order per item, with the right changer
- [X] T045 [P] Write `ado_sim/tests/properties/test_concurrency.py` (SC-003): 20 threads send a conditional update of the same item at the same revision; exactly one succeeds, 19 get 412; the item has exactly one new revision; also a link added while its target is updated leaves both items consistent
- [X] T046 [P] Write `ado_sim/tests/properties/test_timing.py` (SC-004): with 5,000 seeded items, 95% of single-item reads, updates and supported queries finish within 1 s on the test machine (marked so CI reports the measured p95)
- [X] T047 [P] Write `ado_sim/tests/properties/test_seed_time.py` (SC-006): seed and reset from `seed/demo.yaml` each under 1 minute
- [X] T048 [P] Write `ado_sim/tests/properties/test_no_tokens.py` (SC-007): after a run that issues tokens and calls every operation, no token appears in any response body or header (except the issuing command's output), any captured log line, `seed/demo.yaml` or any fixture; the data file holds only hashes; marker strings planted in a field value and a comment (including in a refused request that logs an error) appear in no captured log line (FR-024)

---

## Phase 12: Deployment

- [X] T049 Write `deploy/ado-sim.Dockerfile` (python:3.12-slim, uv 0.10.7, `uv sync --locked --no-dev` from `ado_sim/`, non-root user, data directory `/var/lib/ado-sim`, `ADO_SIM_DB_PATH=/var/lib/ado-sim/ado_sim.db`, entrypoint migrates then serves on 8600); add `ado_sim/` copy rules so the image holds only the simulator
- [X] T050 Add the `ado-sim` service to `deploy/compose.yaml` (image `adlc-ado-sim:0.1.0`, build from `deploy/ado-sim.Dockerfile`, platform network, volume `ado-sim-data:/var/lib/ado-sim`, port `${ADO_SIM_PORT:-8600}:8600`, `ADO_SIM_TOKEN_KEY` required from `.env`, healthcheck on `/health`); the image's entrypoint runs `ado-sim migrate`, then `ado-sim seed --if-new --file seed/demo.yaml` (seeds only when the database has no organisation yet, otherwise does nothing), then `ado-sim serve`; add `ADO_SIM_TOKEN_KEY=REPLACE_ME` and `ADO_SIM_PORT=8600` to `.env.example` under a "# ADO simulator" heading, add both to `COMPOSE_ONLY` in `tests/unit/test_env_example.py`, and make the secret-placeholder check there treat `ADO_SIM_TOKEN_KEY` as a secret
- [X] T051 Add the `ado-sim` process to `deploy/Procfile.local` (`cd ado_sim && env -u VIRTUAL_ENV ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db uv run ado-sim serve`), its settings to `deploy/local.env`, and to `make local-setup` in `Makefile`: `uv sync --locked` in `ado_sim/`, `ado-sim migrate`, and `ado-sim seed --file seed/demo.yaml` when the database is new
- [X] T052 Add `ado-sim-check` to `Makefile` (ruff check and format check, mypy, pytest, coverage report `--fail-under=80`, `ado-sim export-openapi --check`) and call it from `check`, as `pilot-check`

---

## Phase 13: Polish and documentation

- [X] T053 [P] Write `ado_sim/README.md`: what the simulator is (SA §22.2), what it is not (no lifecycle, policy or decision rights), commands, settings, the seed file, tokens, the contract and fixtures, known differences
- [X] T054 [P] Update `deploy/README.md` (the `ado-sim` service, its volume, issuing tokens) and `docs/run-without-docker.md` (the `ado-sim` process, port 8600, issuing a token locally)
- [X] T055 Run `make ado-sim-check`, `uv run pytest tests/unit` (platform boundary and env example) and `uv run python -m scripts.migration_check`; fix anything that fails
- [X] T056 Walk `specs/015-ado-sim-api/quickstart.md` sections 2 and 3 live without Docker and record the outcome (each step's status and result) in `specs/015-ado-sim-api/quickstart.md` under "Results"

---

## Dependencies and execution order

### Phase dependencies

- **Setup (Phase 1)**: none; T001 can run alongside T002–T005.
- **Foundational (Phase 2)**: needs T002; T006 → T007 → T008; T009 → T010 → T011; T012; T013 → T014 → T015; T016 needs T006, T007, T012, T014; T017 needs all of Phase 2.
- **User stories (Phases 3–10)**: need Phase 2. US1 first (US2–US5 build on work items); US2, US3, US4, US5 then in any order; US6 and US7 need only Phase 2; US8 needs every operation (Phases 3–9).
- **Properties (Phase 11)**: need US1–US4 (T044–T046), Phase 2 (T047), US8 (T048).
- **Deployment (Phase 12)**: needs Phase 2 and US8 (the check includes `export-openapi --check`).
- **Polish (Phase 13)**: last.

### Within each user story

Tests first and failing → module → routes → story passes its independent test.

### Parallel opportunities

- T003, T004, T005 together; T018 and T019; T023 and T024; T026 and T027; T030 and T031.
- After US1: US2, US3, US4 and US5 can be worked in parallel (different modules), and US6 and US7 at any time after Phase 2.
- T044–T048 together; T053 and T054 together.

## Parallel example: User Story 1

```text
T018 tests for the patch applier (ado_sim/tests/unit/test_patch.py)
T019 API tests for work items (ado_sim/tests/api/test_work_items.py)
```

## Implementation strategy

### MVP first

1. Phases 1 and 2.
2. Phase 3 (US1): create, read and update with revision checks: the smallest useful simulator.
3. Stop and validate US1's independent test.

### Incremental delivery

US2 (history) and US3 (queries) complete the P1 set the engagement layer (016) depends on; US4–US7 complete the board model; US8 publishes the contract 016 builds against; properties, deployment and documentation finish the feature.
