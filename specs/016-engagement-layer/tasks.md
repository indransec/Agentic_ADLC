---

description: "Task list for 016-engagement-layer"
---

# Tasks: Engagement Layer (board ↔ platform)

**Input**: Design documents from `specs/016-engagement-layer/` (spec, plan, research, data-model, contracts, quickstart)

**Prerequisites**: plan.md and spec.md (Gate 1 approved 2026-11-20, Gate 2 approved 2026-11-21)

**Tests**: Requested. Core modules are test first (constitution IX): mapping schema and rules V-32–V-36, desired state and diff, `classify`, decision inputs, answer splitting, exactly-once bookkeeping and recovery, identity mapping. Write the tests, see them fail, then implement.

**Organization**: by user story (spec US1–US10), after a setup and a foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to
- Paths are relative to the repository root. Platform code is `src/adlc/engagement/`; unit tests `tests/unit/engagement/`; service tests (with the harness fixture `h` of `tests/integration/conftest.py` and `FakeBoard`) `tests/integration/engagement/`; the port contract suite `tests/contract/board/`.
- Names in contracts are mapping keys; no tracker name (type, state, field, decision value, label, area) is written in `src/adlc` (FR-003).

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: confirm the board contract, the package skeleton, settings, accounts and the simulator seed.

- [X] T001 Confirm every board operation in `specs/016-engagement-layer/contracts/board-port.md` against the 015 contract (`ado_sim/contract/openapi.json`, `specs/015-ado-sim-api/contracts/operations.md`, `ado_sim/contract/differences.md`) and a fixture in `ado_sim/contract/fixtures/` (path, method, query parameters including `api-version` and `timePrecision`, body, response shape, refusal statuses 401/404/412); add a "015 operation and fixture" column to the mapping table at the end of `board-port.md`; record any gap (an operation the adapter needs that 015 does not serve) in that file and stop if one exists
- [X] T002 Create `src/adlc/engagement/__init__.py` and `src/adlc/engagement/README.md` (stub naming the modules of plan.md "Project Structure"); add the console script `adlc-board = "adlc.engagement.cli:main"` to `pyproject.toml`; update `tests/unit/test_console_scripts.py` so its list of console scripts includes `adlc-board` (read the test first; if it derives the list from `pyproject.toml`, no change is needed and say so in the commit). Done: the test derives its list from `pyproject.toml`; the script entry is added with the CLI in T051 so it never points at a placeholder
- [X] T003 Add `BoardSettings` to `src/adlc/config/settings.py` (extends `DatabaseSettings`; fields per `contracts/api-cli-settings.md` "Settings": `board_enabled: bool = False`, `board_url`, `board_identities_url` defaulting to `board_url`, `board_organization`, `board_project`, `board_token: SecretStr | None` with `min_length=20` and `_meta(..., secret=True)`, `board_service_identity`, `board_evidence_url`, `board_mapping_file: Path = Path("adlc-specs/tracker_mapping.yaml")`, `board_start_from: str | None`, `board_port: int = 8050`); a model validator that, when `board_enabled`, requires url, organization, project, token, service identity and evidence url and names each missing one; unit tests in `tests/unit/test_settings.py` (defaults, disabled needs nothing, enabled lists every missing name, the token never appears in `repr` or errors)
- [X] T004 [P] Add the `ADLC_BOARD_*` keys to `.env.example` under "# Board engagement (feature 016)" (`ADLC_BOARD_ENABLED=false`, empty URL and identity values, `ADLC_BOARD_TOKEN=` empty because the platform runs without it when disabled; document the forms in comments); include `BoardSettings` in `tests/unit/test_env_example.py::test_keys_match_settings` and treat `ADLC_BOARD_TOKEN` as a secret that must be empty or a placeholder
- [X] T005 Write tests first in `tests/unit/test_accounts_file.py` for the optional `board_identity` per account: accepted when absent; a string `^[^\s]+$` compared case-insensitively; two accounts with the same identity → an error naming both accounts; then add `board_identity: str | None` to `Account` and to `FIELDS` in `src/adlc/identity/accounts.py`; add a commented example to `deploy/accounts.example.yaml`
- [X] T006 [P] Add to `ado_sim/seed/demo.yaml` the custom fields `Custom.AdlcRootCause` (string, "ADLC Root Cause"), `Custom.AdlcReason` (plainText, "ADLC Reason"), `Custom.AdlcReworkTarget` (string, "ADLC Rework Target"), `Custom.AdlcValues` (plainText, "ADLC Values") and `Custom.AdlcEvidenceLink` (string, "ADLC Evidence Link") on every type (the `&adlc_fields` anchor); regenerate the affected 015 fixtures (`work_item_types/*.json`, `fields/list.json`) and review the diff; run `make ado-sim-check`

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: tables, the port and its two adapters with one contract suite, the mapping and its validation, the `source` argument, and the store. No user story can start before this phase is done.

- [X] T007 Write `db/migrations/versions/0002_board.py` exactly as `data-model.md`: `board_link` (PK `object_kind`, `object_id`; `object_kind IN ('usecase','run','clarification')`; `work_item_id` unique), `board_sync_state` (one row, `id = 1` check; `last_poll_outcome IN ('ok','board_unreachable','auth_failed','mapping_invalid')`; `last_error` length ≤ 2000), `board_delivery` (PK `usecase_id` FK `usecase`; `last_error` length ≤ 2000), `board_requeue`, `inbound_change` (PK `work_item_id`, `update_id`; `kind IN ('own','baseline','register_usecase','decide','answer','revert_only','ignored')`), `inbound_outcome` (PK and FK to `inbound_change`; `outcome IN ('accepted','refused','ignored')`; `reason_code IN ('not_mapped','not_authorised','missing_input','invalid_input','stale','already_answered','unknown_value','closed','platform_field','invalid_usecase')` or null; `reason` length ≤ 2000), `board_reconciliation`; append-only triggers (the baseline's `_refuse` pattern) on `board_requeue`, `inbound_change`, `inbound_outcome`, `board_reconciliation`; a working `downgrade`
- [X] T008 Extend `scripts/migration_check.py` to assert the new tables and that UPDATE and DELETE are refused on the four append-only tables; run `uv run python -m scripts.migration_check`
- [X] T009 [P] Write `src/adlc/engagement/model.py` (frozen dataclasses `BoardItem`, `BoardUpdate`, `ChangePage`, `Identity`, `ItemWrite`, `BoardInfo` per `data-model.md` "Board-neutral types") and `src/adlc/engagement/port.py` (`BoardAdapter` Protocol with the operations of `contracts/board-port.md`, and errors `BoardUnreachable`, `BoardAuthFailed`, `ItemNotFound`, `RevisionConflict`, `BoardRefused`; error messages never carry field values)
- [X] T010 Write the port contract suite first in `tests/contract/board/test_port_contract.py`, parametrised over adapters through a fixture `board` (FakeBoard always; the ADO adapter when the simulator fixture is available): create with parent; get; get_at an older revision; update with the right and a stale `expected_rev` (stale → `RevisionConflict`, nothing changed); comment; `changed_since` + `updates` return every update after a watermark exactly once across two calls with changes in between; `find_identity`; unknown item → `ItemNotFound`; `check()` lists types, states, fields and areas; a wrong token → `BoardAuthFailed`
- [X] T011 Write `tests/contract/board/conftest.py`: a session fixture that starts the simulator from this repository (`uv run --project ado_sim ado-sim migrate`, `seed --file ado_sim/seed/demo.yaml`, `token issue adlc-platform@adlc.demo` and one demo user, `serve` on a free port with a temporary `ADO_SIM_DB_PATH` and a random `ADO_SIM_TOKEN_KEY`), waits for `/health`, and stops the process (its own PID, not the `uv` wrapper) at the end; skip with a clear reason when `uv` is missing; mark the suite `board_contract` (register the marker in `pyproject.toml`)
- [X] T012 Write `src/adlc/engagement/fake.py`: `FakeBoard` implementing `BoardAdapter` in memory with revisions, update ids that keep `rev` on link side updates (015 T001), an `as_of` equal to the latest change, a configurable process (types, states, fields), people acting as other identities (`act_as(unique_name)`), and switches to simulate outages (`unreachable`) and auth failure; it passes T010
- [X] T013 Write `src/adlc/engagement/ado.py`: `AdoBoard(settings, client: httpx.Client | None)` implementing the port with the calls listed in `contracts/board-port.md` (Basic auth with the token; `api-version=7.1`, comments `7.1-preview.4`; WIQL with `timePrecision=true`; updates paged with `$top=200`/`$skip`; `test /rev` on every update; 412 → `RevisionConflict`, 401 → `BoardAuthFailed`, 404 → `ItemNotFound`, transport errors and 5xx → `BoardUnreachable` after one connection retry; 10 s timeout); field references and types arrive as data from the mapping, never literals; it passes T010 against the simulator
- [X] T014 [P] Write `tests/contract/board/test_fixture_shapes.py`: every success fixture in `ado_sim/contract/fixtures/` whose operation the adapter uses is decoded by the adapter's readers into board-neutral types without error (so a simulator contract change breaks the platform build)
- [X] T015 Write the mapping schema `adlc-specs/schema/catalogues/tracker_mapping.schema.json` (every key of `contracts/tracker-mapping.md`, `additionalProperties: false`, `inbound.mode` enum `polling`, `poll_interval` in the platform's duration form) and `adlc-specs/tracker_mapping.yaml` with the values of `contracts/tracker-mapping.md` and the ten terminal columns from `ado_sim/seed/demo.yaml`
- [X] T016 Write negative fixtures first for V-32–V-36 under `tests/fixtures/specs/V-32-*/` … `V-36-*/` (`patch.yaml` + `expected.yaml`, the 002 pattern) and positive coverage in the `_valid` bundle (add `tracker_mapping.yaml` to it); then load `tracker_mapping.yaml` in `src/adlc/spec_toolkit/loader.py` as an optional top-level file (`bundle.tracker_mapping`, schema checked at L2) and add rules V-32–V-36 per `contracts/tracker-mapping.md` "Rules" in `src/adlc/spec_toolkit/rules/cross_spec.py`; add the five rows to `specs/002-terminal-spec-toolkit/contracts/validation-rules.md` (the code-and-table test keeps them in step); `make spec-validate` passes
- [X] T017 Write tests first in `tests/unit/engagement/test_mapping.py`, then `src/adlc/engagement/mapping.py`: load and query the mapping (types and fields per item kind, column for a terminal, item state and sub-stage for a run state, decision value ↔ action, inputs with field and label, platform-written fields, poll interval); `check_against(board_info)` returns every gap by name (type, state, field, area missing; parent relation missing); a broken file raises an error naming the file and path
- [X] T018 Write tests first in `tests/unit/engagement/test_identities.py`, then `src/adlc/engagement/identities.py`: map a board unique name to an `Actor` (account name, roles from the accounts file) using the mapping's `identities.match`; unknown → `None`; the service identity never maps to an account (startup error if an account claims it)
- [X] T019 Add an optional keyword `source: Mapping[str, Any] | None = None` to `OrchestratorService.submit_usecase`, `decide`, `decide_waiver`, `complete_escalation` and `answer_clarification` in `src/adlc/orchestration/service.py`, recorded as `"source"` in the run activity `detail` of the step the call writes (for `submit_usecase`, in the use case's first activity or a `usecase_source` detail the store can look up); no rule changes; unit tests in `tests/integration/orchestration/` show the source recorded and the inbox path unchanged
- [X] T020 Write `src/adlc/engagement/store.py`: every SQL statement of the board tables (link get/put by object or by item; sync state read/write; delivery mark dirty, take due, success, failure with the outbox's `RETRY_DELAYS` and `MAX_ATTEMPTS` imported from `adlc.orchestration.outbox`, dead letter, requeue; claim a change, write an outcome, list claimed-without-outcome; reconciliation insert and read); each function takes the caller's connection; tests in `tests/integration/engagement/test_store.py`

**Checkpoint**: both adapters pass one contract suite; the mapping validates and checks against the board; the tables and store work.

---

## Phase 3: User Story 1 – See the lifecycle on the board (P1) 🎯 MVP

**Goal**: every use case, run and clarification round projected to the board after the platform commits, with retries and dead letters.

**Independent Test**: submit a use case in the inbox and run it to its first sign-off with FakeBoard: one Epic in the first terminal's column with sub-stage "Awaiting sign-off", one run item with the evidence link and decision values, ids on both; each later transition follows.

### Tests (write first)

- [X] T021 [P] [US1] `tests/unit/engagement/test_desired.py`: desired state for a use case with no runs, one open run, a run awaiting sign-off (description lists the form's decision values, inputs per value, root causes and terminals, emitted values, reviewer recommendation, pending waiver), an escalated run, a closed run and the next terminal opened, a terminated use case (Epic `terminated` state, items `terminated`), a clarification round open and answered; the hash changes exactly when a platform-written value changes; the `clear` set is the decision, input and answer fields
- [X] T022 [P] [US1] `tests/integration/engagement/test_projection.py` with `h` and FakeBoard: the Independent Test above; decisions made through `OrchestratorService` (the inbox path) appear on the board (FR-009); the projector creates items in parent order and records `board_link`; a second pass with nothing new writes nothing

### Implementation

- [X] T023 [US1] `src/adlc/engagement/desired.py`: `desired(snapshot, mapping, evidence_url) -> list[DesiredItem]` (pure) and `snapshot(conn, usecase_id)` reading `usecase`, `terminal_run`, `clarification_round`, `clarification_answer`, `waiver`, and the run's decision form via `adlc.inbox.forms.build_form` with a role-less system `Actor`
- [X] T024 [US1] `src/adlc/engagement/projector.py`: find dirty use cases from the projection cursor (new rows in `run_transition`, `run_activity`, `clarification_round`, `clarification_answer`, `waiver`, `usecase`), mark them in `board_delivery`, and deliver due ones oldest first: compute desired items, create missing items (parent first) and link them, write changed platform-written fields with `expected_rev` (on `RevisionConflict` re-read and retry once), skip clearing person-input fields unless `inbound_update_id` ≥ the item's latest update (research R-09); success clears the delivery; failure schedules the next attempt or dead-letters
- [X] T025 [US1] Board outage behaviour in `tests/integration/engagement/test_projection.py`: with FakeBoard `unreachable`, platform operations succeed and nothing waits; deliveries retry on the outbox schedule (time-scaled clock) and dead-letter on the fifth failure; `requeue` recomputes from current state and delivers

**Checkpoint**: the board follows the platform.

---

## Phase 4: User Story 2 – Decide a run from the board (P1)

**Goal**: `pass`, `rework`, `exception`, `terminate` saved on a run item become the inbox's decisions, exactly once, with refusals reverted.

**Independent Test**: as an approver on FakeBoard set `Pass` on a run awaiting sign-off → the run closes (or waits for the next approver), the ledger records that person with the board item as source, the Epic moves; `Rework` with no root cause → refused, reverted, reason commented.

### Tests (write first)

- [X] T026 [P] [US2] `tests/unit/engagement/test_classify.py`: per `contracts/inbound-rules.md` §1–§2: own updates; unmapped changer; decision field set on a run item; decision cleared (ignored); a platform-written field change plus a decision in one update (both actions); changes to unread fields ignored; a closed item refuses; property test (hypothesis) that `classify` is total and deterministic
- [X] T027 [P] [US2] `tests/unit/engagement/test_inputs.py`: per `contracts/inbound-rules.md` §3: inputs from fields; from comment lines when fields are empty (`root cause: x`, `reason: y`, `rework target: T2`, `value risk_tier: high`); the field wins over a differing line (and the result says so); the rest of the comment kept as the comment; unknown labels stay comment text; labels are case-insensitive with surrounding spaces ignored; a repeated label → `invalid_input`; values checked against the form (unknown root cause, terminal not offered, wrong value type → `invalid_input` naming the input and allowed values); missing required input → `missing_input`; a comment over 4,000 characters or a reason over 2,000 → `invalid_input` naming the limit (spec Edge Cases)
- [X] T028 [P] [US2] `tests/integration/engagement/test_exactly_once.py` (it needs the database): claiming the same (item, update) twice is a no-op; a claim without outcome found on start is resolved `accepted` when the run activity carries its `source`, and re-applied when not; the outcome is written once
- [X] T029 [US2] `tests/integration/engagement/test_decide.py` with `h` and FakeBoard: each acceptance scenario of spec US2 (pass by a still-needed role; two approvers with the field cleared between; inputs from fields and from comment lines; missing input refused and reverted; not authorised refused and reverted (D-12); the same update read twice has one effect; a decision on a run decided meanwhile in the inbox refused as `stale`)

### Implementation

- [X] T030 [US2] `src/adlc/engagement/classify.py` (pure, per T026)
- [X] T031 [US2] `src/adlc/engagement/inputs.py`: `read_inputs(fields_at_rev, comment, mapping, form) -> Inputs | Refusal` (pure, per T027)
- [X] T032 [US2] `src/adlc/engagement/inbound.py`: one poll (`changed_since(watermark)`, `updates` per item after `inbound_update_id`, in order), classify, claim (`inbound_change`), read the item `get_at` the update's revision, apply through `OrchestratorService` as the mapped `Actor` with `source={"board_item": id, "update": n}` (`decide` with `expected_version` read just before; one retry on `StaleRun`), map exceptions to reason codes per `contracts/inbound-rules.md` §4, write the outcome, and reply per §5 (accepted comment; refused: restore the request's fields to their values before the update, if still unchanged since, and comment `ADLC: refused — <reason>`); advance the watermark only after every item of the poll is done (FR-010); on the first poll with no stored watermark (FR-010a, research R-04) query once, record each returned item's latest update as an `inbound_change` of kind `baseline`, store the answer's `asOf`, and process nothing (or start from `ADLC_BOARD_START_FROM` when set)
- [X] T033 [US2] Recovery on start in `src/adlc/engagement/inbound.py` per research R-07 (claimed without outcome → look up `source` in `run_activity` → accepted or re-apply), covered by T028

**Checkpoint**: sign-off decisions work from the board.

---

## Phase 5: User Story 3 – Register a use case from the board (P1)

**Goal**: a new Epic by a mapped person in the mapped area becomes a use case.

**Independent Test**: create an Epic on FakeBoard as a mapped person → one use case with that name and intake text, submitted by that person; the Epic gets the use case id and the first terminal's column.

- [X] T034 [P] [US3] Tests first in `tests/integration/engagement/test_register.py`: each acceptance scenario of spec US3 (registered once; the person's column ignored and set by the platform; empty description or unmapped user → comment, no use case; an edit after a refusal is a new request; an Epic created by the projector is never registered; an Epic outside the mapped area ignored)
- [X] T035 [US3] `register_usecase` in `src/adlc/engagement/inbound.py`: title → name, description converted from HTML to plain text → intake text; call `submit_usecase` with `source`; link the Epic to the new use case in `board_link` in the same step as the outcome; mark the use case dirty so the projector writes its id and column

---

## Phase 6: User Story 4 – Answer a clarification from the board (P2)

**Goal**: answers saved on a clarification item reach the platform.

**Independent Test**: with a run awaiting clarification, save numbered answers on its Task as the addressed role → the run continues; the Task closes.

- [X] T036 [P] [US4] Tests first in `tests/unit/engagement/test_answers.py`: split numbered answers (`1.`, `2)`, blank lines between), one-question rounds take the whole text, count mismatch → `invalid_input` naming expected and given counts
- [X] T037 [P] [US4] Tests first in `tests/integration/engagement/test_answer.py`: each acceptance scenario of spec US4 (answered by the addressed role; wrong role refused and cleared; count mismatch refused; already answered in the inbox → `already_answered`)
- [X] T038 [US4] `answer` in `src/adlc/engagement/inbound.py` and the splitter in `src/adlc/engagement/inputs.py`; call `answer_clarification` with `source`

---

## Phase 7: User Story 5 – Waivers, escalations and termination (P2)

**Goal**: `Exception` proposes a waiver; `Approve waiver` / `Reject waiver` decide it; `Complete escalation`; `Terminate` with a reason.

**Independent Test**: `Exception` with a reason → pending waiver shown on the run item; a different approver sets `Approve waiver` → recorded; an escalated run completed from the board returns to awaiting sign-off.

- [X] T039 [P] [US5] Tests first in `tests/integration/engagement/test_waiver_escalation.py`: each acceptance scenario of spec US5, including the proposer approving their own waiver refused (separation of duties) in all four combinations of board and inbox for proposal and approval; terminate without a reason refused
- [X] T040 [US5] Waiver, escalation and terminate actions in `src/adlc/engagement/inbound.py` (`decide_waiver` on the run's `pending_waiver_id`; `complete_escalation` with `{}` artifacts; `decide(..., "terminate", reason=...)`), and the pending waiver and its approver roles in `src/adlc/engagement/desired.py`

---

## Phase 8: User Story 6 – The board cannot get ahead of the platform (P2)

**Goal**: platform-written fields restored; unmapped users refused; reverts never re-read as requests.

**Independent Test**: move an Epic to a later column → restored with a comment; an unmapped user's decision → reverted "not a mapped platform user".

- [X] T041 [P] [US6] Tests first in `tests/integration/engagement/test_guards.py`: each acceptance scenario of spec US6; a revert written by the service account is recorded as `own` on the next poll; a revert does not overwrite a later person's change to the same field (the item's current value is compared first); a refusal to an unmapped user names no role or run state (checklist CHK021)
- [X] T042 [US6] Platform-field reverts and the unmapped refusal in `src/adlc/engagement/inbound.py`, using `platform_written` from the mapping and the platform's current desired values from `desired.py`

---

## Phase 9: User Story 7 – Reconcile the board with the platform (P2)

**Goal**: the CoE corrects drift on demand; a report lists each difference.

**Independent Test**: change three things on FakeBoard behind the sync's back; reconcile → three differences reported and fixed; a second run reports none.

- [X] T043 [P] [US7] Tests first in `tests/integration/engagement/test_reconcile.py`: each acceptance scenario of spec US7 (differences corrected and listed with board values hashed; missing items created and linked; refused for a person without the role in `ADLC_DEADLETTER_ROLE`; platform tables unchanged, compared before and after); reconciliation skips person-input fields that inbound sync has not yet read (CHK011)
- [X] T044 [US7] `src/adlc/engagement/reconcile.py`: `reconcile(actor) -> Report` using `desired.py` without the hash shortcut and the board's actual items; record `board_reconciliation`
- [X] T045 [US7] `src/adlc/api/routes/board.py`: `POST /board/reconciliations`, `GET /board/reconciliations/{id}`, `POST /board/requeue/{usecase_id}` (403 unless the session holds `ADLC_DEADLETTER_ROLE`); register the router in `src/adlc/api/app.py`; API tests in `tests/integration/api/test_board_routes.py`

---

## Phase 10: User Story 8 – A validated tracker mapping (P2)

**Goal**: the mapping fails fast, by name, before the sync runs.

**Independent Test**: remove a terminal's column → `make spec-validate` fails naming it; map a field the board lacks → `adlc-board check-mapping` fails naming it and `adlc-board run` does not start syncing.

- [X] T046 [P] [US8] `tests/integration/engagement/test_mapping_check.py`: the board check against FakeBoard and against the simulator (contract marker): every gap kind reported by name; a wrong token reported as authentication; the sync state shows `mapping_invalid` and nothing is polled or projected
- [X] T047 [US8] Extend `tests/unit/test_no_hardcoded_values.py`: no type, state, field reference, decision value, input label or area from `adlc-specs/tracker_mapping.yaml` appears in `src/adlc` (the mapping file and tests excepted)

---

## Phase 11: User Story 9 – Sync health and resilience (P3)

**Goal**: the `adlc-board` process, health data, first start, outages and restarts.

**Independent Test**: stop FakeBoard (`unreachable`) for longer than a poll while people change items, then start it → every change processed once; health shows the watermark age rising then falling.

- [X] T048 [P] [US9] Tests first in `tests/integration/engagement/test_health_resilience.py`: health fields of `contracts/api-cli-settings.md`; restart between polls resumes from the stored watermark; first start against a board with history records `baseline` for every existing item and replays nothing (FR-010a), and `ADLC_BOARD_START_FROM` overrides it; a failed item in a poll leaves the watermark unchanged; a revoked token → `auth_failed`, the platform unaffected
- [X] T049 [US9] `src/adlc/engagement/health.py` (from the sync tables, no values) and `GET /board/health` in `src/adlc/api/routes/board.py`
- [X] T050 [US9] `src/adlc/engagement/worker.py`: `adlc-board run`: load settings; when disabled, serve `/health` (`{"status": "disabled"}`) on `ADLC_BOARD_PORT` and idle; else check the mapping against the board (retry with back-off while unreachable, `mapping_invalid` stops syncing), recover claims (T033), then loop every `poll_interval`: inbound poll, then projector deliveries; `/health` reports `ok`, `degraded` (board unreachable or auth failed) or `mapping_invalid`; spans and log lines per research R-17 (no values, no token)
- [X] T051 [US9] `src/adlc/engagement/cli.py`: `run`, `check-mapping`, `reconcile --as <account>`, `health`, `requeue <usecase_id> --as <account>` with the exit codes of `contracts/api-cli-settings.md`; tests in `tests/unit/engagement/test_cli.py`

---

## Phase 12: User Story 10 – One contract suite for every adapter (P3)

**Goal**: the suite and the boundaries are complete and run in `make check`.

**Independent Test**: the suite passes on both adapters; a simulator answer changed on purpose makes it fail naming the case.

- [X] T052 [US10] Complete `tests/contract/board/test_port_contract.py` with every adapter operation the engagement layer calls (cross-check with `grep` of `board.` calls in `src/adlc/engagement/`), including refusals (stale revision, unknown item, no token); make sure `make test` runs it (marker included by default, skipped with a reason only when `uv` is absent)
- [X] T053 [P] [US10] Keep `tests/unit/test_ado_sim_boundary.py` and `ado_sim/tests/test_boundary.py` passing; add a check that `src/adlc/engagement/ado.py` is the only module importing `httpx` among `src/adlc/engagement/`

---

## Phase 13: Properties (success criteria across stories)

- [X] T054 [P] `tests/integration/engagement/test_property_exactly_once.py` (SC-003): 500 board changes by several people across 20 use cases on FakeBoard, with overlapping polls (a watermark moved back on purpose) and a worker restart in the middle; every change processed once, in update order per item; the platform's records equal those of the same decisions made through the inbox, one for one
- [X] T055 [P] `tests/integration/engagement/test_property_refusals.py` (SC-004): a scripted set covering every reason code; 100% reverted with a comment naming the reason; platform tables unchanged by any of them
- [X] T056 [P] `tests/integration/engagement/test_property_outage.py` (SC-005): a 10-minute board outage (time-scaled clock) with changes on both sides; afterwards all delivered, none lost or duplicated
- [X] T057 [P] `tests/integration/engagement/test_property_reconcile.py` (SC-006): 50 use cases, 10 injected differences, all reported and corrected, the second run reports none, under 1 minute
- [X] T058 [P] `tests/integration/engagement/test_property_lifecycle.py` (SC-007): one use case driven entirely from FakeBoard through sign-offs, a rework with root cause, an exception and waiver, a clarification, an escalation completion and a termination of a second use case; its ledger records, decision log and activity match an inbox-driven run in kind and attribution
- [X] T059a [P] `tests/integration/engagement/test_no_values_logged.py` (FR-023, constitution XI): plant marker strings in a decision comment, a reason field, an answer, a refused input and an unmapped user's change; run polls, projections and a reconciliation with `caplog` and an in-memory span exporter; no marker and no board token appears in any log line, span name or span attribute
- [X] T059 [P] `tests/integration/engagement/test_property_latency.py` (SC-001, SC-002): with a 10 s interval and the worker loop on FakeBoard, 95% of board decisions applied and shown within 30 s and 95% of platform changes on the board within 15 s; report the measured p95 in the test summary (as 015's property tests)

---

## Phase 14: Deployment

- [X] T060 Add the `board` service to `deploy/compose.yaml` (image `adlc-api:0.1.0`, command `adlc-board run`, platform network, the database volume and settings like the orchestrator, the accounts file mount, `ADLC_BOARD_*` from `.env` with `ADLC_BOARD_URL` defaulting to `http://ado-sim:8600`, `depends_on` `migrate` (completed) and `ado-sim` (healthy), healthcheck on `http://127.0.0.1:8050/health`); `make up --wait` must pass with `ADLC_BOARD_ENABLED=false`
- [X] T061 [P] Add the `board` process to `deploy/Procfile.local` (`uv run adlc-board run`) and `ADLC_BOARD_URL=http://127.0.0.1:8600` to `deploy/local.env`
- [X] T062 [P] Update `deploy/README.md` (the `board` service, turning it on, issuing the service token, `board_identity` in the accounts file) and `docs/run-without-docker.md` (the `board` process, port 8050, the same steps without Docker)

---

## Phase 15: Polish and documentation

- [X] T063 [P] Write `src/adlc/engagement/README.md`: what the engagement layer does and does not do, modules, the flow of a change in each direction, the mapping, identities, health, reconciliation, and how to point it at real ADO (settings only, then run the contract suite against it)
- [X] T064 [P] Add a short "Built in 016" note to SA §22.3 in `docs/solution-architecture.md` (state-based projection with the outbox's retry rule, own process, `board_identity` in the accounts file, first start not replaying history) and mark §8 and §13 as superseded where 016 changes them (SA §22.10 table)
- [X] T065 Run `make check` pieces locally: `uv run pytest tests/unit tests/integration/engagement tests/contract/board`, `make spec-validate`, `uv run python -m scripts.migration_check`, `make ado-sim-check`; fix anything that fails
- [X] T066 Walk `specs/016-engagement-layer/quickstart.md` sections 2 and 3 live without Docker against the simulator (a scratch database for the platform and the simulator, so `data/local/` is untouched unless the user asks) measure the time from saving a decision on the board to the run's new state on the board (SC-001) and from a platform change to the board (SC-002), and record each step's status and result under "Results" in `specs/016-engagement-layer/quickstart.md`

---

## Dependencies and execution order

### Phase dependencies

- **Setup (Phase 1)**: none; T001 first (it may stop the feature).
- **Foundational (Phase 2)**: needs Setup; blocks every story. T010 before T012 and T013; T016 before T017; T007 before T020.
- **US1 (Phase 3)**: needs Phase 2. Every later story's board replies rely on the projector (T024).
- **US2 (Phase 4)**: needs US1. **US3–US6** need US2's `inbound.py` (T032) and can then run in parallel with each other (different test files; implementation tasks touch `inbound.py` in sequence).
- **US7 (Phase 9)**: needs US1. **US8 (Phase 10)**: needs Phase 2. **US9 (Phase 11)**: needs US1 and US2. **US10 (Phase 12)**: needs Phase 2.
- **Properties (Phase 13)**: need US1–US9. **Deployment (Phase 14)**: needs US9 (the process). **Polish (Phase 15)**: last; T066 after everything.

### Within each user story

- Tests first, failing; then the implementation; then the story's integration test passes.
- Pure modules (`desired`, `classify`, `inputs`) before the modules that call them.

### Parallel opportunities

- T004, T006 with T003 and T005; T009 with T007–T008; T014 with T015–T018.
- In each story, the test tasks marked [P].
- T054–T059 together; T061–T062 together; T063–T064 together.

## Parallel example: User Story 2

```text
T026 tests/unit/engagement/test_classify.py
T027 tests/unit/engagement/test_inputs.py
T028 tests/unit/engagement/test_exactly_once.py
```

then T030 and T031 (different files), then T032–T033.

## Implementation strategy

### MVP first

Phases 1–3 (US1): the board shows the lifecycle; nothing on the board can change the platform yet,
so it is safe to run beside the inbox.

### Incremental delivery

1. US1 projection → the board is a live view.
2. US2 and US3 → a lifecycle can be started and signed off from the board (the core of Option A).
3. US4–US6 → every inbox decision available on the board, with guards (D-12).
4. US7–US9 → reconciliation (D-13), mapping checks, health and resilience.
5. US10, properties, deployment, docs, the live walk.
