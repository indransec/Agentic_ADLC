# Tasks: Evidence Ledger

**Input**: Design documents from `specs/005-evidence-ledger/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Constitution IX makes these test-first: record content version 2 and
hashing, profile merge, verification rules, and the content store with its file checks. Test
tasks come first in each phase and must fail before their implementation.

**Organization**: phases follow the spec's user stories in priority order (US1–US4 P1, US5 P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US5)

## Conventions used by every task

- Code lives in `src/adlc/ledger/`, unit tests in `tests/unit/ledger/`, and database tests in
  `tests/integration/ledger/`. Database tests use the shared `h` and `orch_template` fixtures.
- The ledger never opens its own transaction during a close. It works on the orchestrator's
  connection, so the record, versions, profile and event commit together.
- No terminal ids, event names, role names or artifact ids in `src/adlc/ledger/` (constitution
  I).

---

## Phase 1: Setup

- [ ] T001 Add `openpyxl` to the dependencies in `pyproject.toml` (and refresh `uv.lock`) and record it (MIT) in the plan's licence table if it is not already there
- [ ] T002 Add the settings to `RuntimeSettings` in `src/adlc/config/settings.py`, writing the tests first in `tests/unit/test_settings.py`:
  - `file_store_dir: Path` (`ADLC_FILE_STORE_DIR`, default `data/files`);
  - `attachment_max: int` (`ADLC_ATTACHMENT_MAX`, default `25MB`, parsed as bytes, where `MB` means 10^6; a bare number is bytes);
  - `attachment_types: frozenset[str]` (`ADLC_ATTACHMENT_TYPES`, a comma list, defaulting to the seven media types of contracts/storage.md).

  Document them in `.env.example`, keep `tests/unit/test_env_example.py` green, and ignore `data/files/` in `.gitignore`.
- [ ] T003 [P] Write failing migration tests in `tests/integration/ledger/test_migration_0005.py`, following data-model.md:
  - **content_blob**: `ledger.content_blob` (`content_hash` PK matching `^sha256:[0-9a-f]{64}$`).
  - **ledger tables**: `ledger.file_object`; `ledger.profile_version` (PK `(usecase_id, version)`, version ≥ 1); `ledger.verification_run`.
  - **run tables**:
    - `run.artifact_version`, with PK `(run_id, artifact_id, version)`, version ≥ 1, `producer_type` in (`agent`, `person`), and FK to `content_blob`;
    - `run.artifact_attachment`, with `file_name` of 1–255 characters and no `/` or `\`;
    - `run.checklist_result`;
    - `run.terminal_run.profile_version`, an integer that is not null, default 0.
  - **views**: `run.v_run_step` and `run.v_usecase_terminal_summary`.
  - **append-only**: every new table refuses UPDATE, DELETE and TRUNCATE for app and owner.
  - **grants**: the app role has exactly SELECT and INSERT on every new table, and SELECT on both views.
  - **round trip**: a downgrade to 0004 and an upgrade again work.
- [ ] T004 Write `db/migrations/versions/0005_evidence_ledger.py` (reusing `run.reject_mutation()`) so T003 passes
- [ ] T005 [P] Create the skeleton:
  - `src/adlc/ledger/__init__.py` and `src/adlc/ledger/README.md` (a stub);
  - `adlc-ledger = "adlc.ledger.cli:main"` in `pyproject.toml`;
  - `*/adlc/ledger/*` added to `CORE_MODULES` in `Makefile`;
  - a named volume `adlc-files` mounted at `/var/lib/adlc/files` in the `api` and `orchestrator` services of `deploy/compose.yaml`, with `ADLC_FILE_STORE_DIR=/var/lib/adlc/files`;
  - a note in the deployment README that this volume must be backed up with the database.

**Checkpoint**: settings load; migration 0005 applies and reverts.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [ ] T006 [P] Write failing tests in `tests/unit/ledger/test_storage.py` for `FileStore` and the file checks (contracts/storage.md):
  - a file is stored at `<root>/<aa>/<bb>/<hex>` and read back; storing it twice keeps one file;
  - its hash is `sha256:` plus the SHA-256 of the bytes;
  - each refusal (`AttachmentRefused`) has its own case:
    - over the size limit;
    - a type not on the allow list;
    - a `.docx` that is not a ZIP;
    - an `.xlsx` containing `xl/vbaProject.bin` (macros);
    - a PDF without `%PDF-`;
    - a PNG without its signature;
    - an SVG or text file that is not UTF-8;
    - an unwritable root.
- [ ] T007 [P] Write failing tests in `tests/unit/ledger/test_content.py` for record content version 2 (contracts/record.md):
  - `build_v2(...)` has exactly the documented keys, with artifacts in spec order, and `null` rather than a missing key for absent values;
  - the hash is stable under key reordering and changes when an artifact hash changes;
  - `content_version(record)` returns 1 for 003 records (no key) and 2 for new ones.
- [ ] T008 [P] Write failing tests in `tests/unit/ledger/test_binding.py` for `resolve_bound_to(spec, artifacts_of)`:
  - follows the spec's `evidence.ledger.bound_to` (for example `T3.candidate_package.sha256`) to the first row's column of the bound terminal's latest artifacts;
  - gives `None` without a binding, or when the terminal or column is missing.

### Implementation

- [ ] T009 [P] Implement `src/adlc/ledger/storage.py`: the `ContentStore` protocol, `SqlContentStore` (`put_structured` with `INSERT … ON CONFLICT DO NOTHING`, and `get_structured`, both on the caller's connection), `FileStore` (temporary file, atomic rename, content sniffing per contracts/storage.md), and `LedgerContentStore` composing them; SQL in `src/adlc/ledger/store.py`; storing a file runs in `tracing.span("ledger", "store_file")` (T006)
- [ ] T010 [P] Implement `src/adlc/ledger/content.py`: `build_v2`, `content_version` and `record_hash` (reusing `adlc.spec_toolkit.normalise.content_hash`) (T007)
- [ ] T011 Implement `src/adlc/ledger/binding.py` (T008). Make `SqlEvidenceProvider._bound_to` in `src/adlc/policy/evidence.py` call it, so 004 and 005 share one rule, keeping 004's `test_evidence_provider.py` green.

**Checkpoint**: storage, record content and binding are proven in isolation.

---

## Phase 3: User Story 1 – Every closed run leaves a complete, verifiable record (P1) 🎯 MVP

**Goal**: closing writes a version-2 record that references artifact versions by hash, with the profile version and `bound_to`.

**Independent test**: close T1. Every artifact hash in its record resolves to stored content with the same hash, and its previous hash equals T0's record hash.

### Tests first

- [ ] T012 [P] [US1] Write failing integration tests in `tests/integration/ledger/test_record.py`:
  - US1/AC1: a closed run's record has every version-2 key, written in the same transaction as the outcome event (an injected failure after the record leaves neither).
  - US1/AC2: each artifact `content_hash` resolves to stored content that re-hashes to itself.
  - US1/AC3: the chain links records in close order.
  - US1/AC4: T4–T7 records carry `bound_to` equal to the T3 package hash.
  - US1/AC5: UPDATE and DELETE on records and `content_blob` are refused.

### Implementation

- [ ] T013 [US1] Make `_write_ledger` in `src/adlc/orchestration/engine.py` build version-2 content through `adlc.ledger.content.build_v2`. It reads the run's current artifact versions (from US2's table once it exists; until then, it stores each current artifact's content with `put_structured` and lists the hashes), plus `profile_version` (0 until US3) and `bound_to` (`binding.py`) (T012).

**Checkpoint**: records are version 2 and hash-referenced.

---

## Phase 4: User Story 2 – Artifacts stored once, every version kept (P1)

**Goal**: agent and human versions, attachments, spreadsheet uploads, and edits that reset approvals and re-run controls.

**Independent test**: an agent builds T1 (v1); an owner edits `kpis` (v2) with the spreadsheet attached. The history shows v1 (agent) and v2 (person, derived from v1, with the attachment), and the record lists v2.

### Tests first

- [ ] T014 [P] [US2] Write failing unit tests in `tests/unit/ledger/test_spreadsheet.py` (contracts/artifacts.md):
  - the sheet named after the artifact is used, else the only sheet;
  - headers come from row 1, trimmed;
  - empty rows are skipped;
  - numbers, booleans and dates (as ISO text) keep their kind;
  - a formula without a saved value reads as an empty cell;
  - several sheets with none named after the artifact raises `InvalidUpload`, as does a file that is not a workbook.

  Build the workbooks in the test with openpyxl.
- [ ] T015 [P] [US2] Write failing unit tests in `tests/unit/ledger/test_versions.py` for the pure rules:
  - `schema_valid(rows, declared_columns)`;
  - `changed(current_hash, new_content)` (key order ignored, row order matters);
  - the next version number and `derived_from`.
- [ ] T016 [P] [US2] Write failing integration tests in `tests/integration/ledger/test_artifact_versions.py`:
  - US2/AC1: each build attempt writes agent versions with `attempt`.
  - US2/AC2: `edit_artifact` by a sign-off or accountable role holder writes a `person` version derived from the current one, and the run's artifacts become the latest; a non-holder raises `NotAuthorised`; a run in another state raises `InvalidTransition`.
  - US2/AC3: an unchanged edit writes no version.
  - US2/AC4: rows missing a declared column store `schema_valid = false`.
  - US2/AC5: `attach_file` stores the file once (attaching it twice keeps one `file_object`).
  - US2/AC6: `upload_spreadsheet` turns a workbook into rows, attaches the `.xlsx`, and refuses a workbook with no fitting sheet.
  - An edit while awaiting sign-off clears earlier pass approvals (a second approval is needed again), withdraws a pending waiver (status `rejected`, comment "withdrawn: artifact edited"), and re-runs controls, so a broken edit shows a failing control with its reason.
  - An edit makes a decision taken with the old run version raise `StaleRun`.
  - SC-006: identical content across two runs uses one `content_blob` row.
  - SC-004: the human-edit share can be computed from the versions.

### Implementation

- [ ] T017 [P] [US2] Implement `src/adlc/ledger/spreadsheet.py` (T014)
- [ ] T018 [US2] Implement `src/adlc/ledger/artifacts.py`: `ArtifactVersions.record(conn, run, artifacts, producer, attempt)` (in `tracing.span("ledger", "record_versions")`), `current(conn, run_id)` and `history(conn, run_id, artifact_id)` (T015)
- [ ] T019 [US2] In `src/adlc/orchestration/engine.py`, make `StoreArtifacts` (agent results and escalation completion) write versions through `ArtifactVersions` on the same connection. `_write_ledger` then lists the current versions with their attachments.
- [ ] T020 [US2] Implement `LedgerService.edit_artifact`, `upload_spreadsheet`, `attach_file` and `artifact_history` in `src/adlc/ledger/service.py`. Authorisation reuses the orchestrator's sign-off and accountable roles. Each edit:
  - bumps the run's `version`;
  - writes a `sign_off` activity row with outcome `edited`;
  - clears approvals and withdraws the waiver (new orchestrator signal kind `artifact_edited`, from a human actor, allowed in `awaiting_sign_off` and `escalated`, with a transition-table row and tests in `tests/unit/orchestration/test_states.py`, a row in `specs/003-lifecycle-orchestration/contracts/state-machine.md`, and a hypothesis property in `tests/unit/orchestration/test_state_properties.py` that `artifact_edited` never closes a run and never escalates);
  - re-runs the controls through the policy engine and stores the results.

  This makes T016 pass.

**Checkpoint**: version history and human edits work end to end.

---

## Phase 5: User Story 3 – The use-case profile is versioned (P1)

**Goal**: profile versions from emitted values; runs record their version; 004 reads it.

**Independent test**: after T0, T1 and T2 pass, the profile is at version 3. A T3 run records version 3, and `param.*` uses a profile value that is within the guardrail.

### Tests first

- [ ] T021 [P] [US3] Write failing unit tests in `tests/unit/ledger/test_profile.py` for `merge(previous, emitted)`:
  - values of the same name are replaced and others kept;
  - a table replaces the old table whole;
  - an artifact reference is stored as `{artifact, version, content_hash}`;
  - `proposed_parameter(value)` keeps a plain value and takes `value` from a mapping.
- [ ] T022 [P] [US3] Write failing integration tests in `tests/integration/ledger/test_profile.py`:
  - US3/AC1: pass and exception closes write a new version; rework and terminate do not.
  - US3/AC2: a re-pass after rework supersedes values in a new version, and old versions stay readable.
  - US3/AC3: a run records the version current at open and keeps reading it after a newer version appears.
  - US3/AC4 and SC-005: a profile value for `autonomy_level_max` that is within the guardrail is used by `param.*`, and a looser one is rejected and recorded in `run.run_parameter_set.rejected`.
  - US3/AC5: version 0 before any pass.
  - `profile.<name>` in an expression reads the run's version, not labelled synthetic.

### Implementation

- [ ] T023 [US3] Implement `src/adlc/ledger/profile.py`:
  - `merge`;
  - `ProfileVersions.on_close(conn, run, status, emitted)` (in `tracing.span("ledger", "profile_version")`);
  - `current(conn, usecase_id)`;
  - `for_run(conn, run_id)`;
  - `SqlProfileSource` implementing the extended `ProfileSource.values(usecase_id, run_id=None)`.

  This makes T021 pass.
- [ ] T024 [US3] Wire the profile in:
  - `src/adlc/orchestration/engine.py`: `open_in` records `profile_version`, and `_close` calls `on_close` in the close transaction;
  - `src/adlc/policy/parameters.py`: extend the `ProfileSource` protocol, and have `ParameterService` pass `run_id`;
  - `src/adlc/policy/evidence.py`: a `profile` source from the run's version;
  - `src/adlc/policy/factory.py`: `build_policy_engine` uses `SqlProfileSource` by default.

  This makes T022 pass.

**Checkpoint**: guardrail resolution sees approved use-case values.

---

## Phase 6: User Story 4 – Anyone can verify a use case's evidence (P1)

**Goal**: verification of every record, artifact, attachment and binding, with tamper detection, as a CLI and a service.

**Independent test**: a T0→T8 use case verifies clean; corrupting one stored artifact as superuser is reported with the record, artifact, and expected and actual hash.

### Tests first

- [ ] T025 [P] [US4] Write failing unit tests in `tests/unit/ledger/test_verify_rules.py` for the pure checks, applied to in-memory records and store stubs:
  - `content`, `chain`, `artifact`, `attachment` and `binding`, each with a passing and a breaking case;
  - version-1 records are checked for content and chain only;
  - breaks never contain artifact content.
- [ ] T026 [P] [US4] Write failing integration tests in `tests/integration/ledger/test_tamper.py`, using the superuser connection with `SET session_replication_role = replica` to bypass the append-only triggers:
  - a clean T0→T8 lifecycle verifies, including version-1 records written before the switch (SC-002);
  - each SC-003 case is reported with its record and element: altered record content, an altered `content_blob` body, a deleted attachment file, a broken `previous_record_hash`, and a `bound_to` that differs from T3's package hash;
  - `ledger.verification_run` rows record actor, scope, records checked, breaks and `verified`;
  - verifying `all` is one row;
  - SC-007: 10 closed runs, each with 3 attachments of 1 MB, verify in under 2 s.
- [ ] T027 [P] [US4] Write failing tests in `tests/integration/ledger/test_cli.py` for `adlc-ledger verify --usecase UC-0001 [--json]`: exit 0 when verified, 1 with breaks, and 2 on a configuration error; the JSON has the report shape of contracts/verification.md.

### Implementation

- [ ] T028 [US4] Implement `src/adlc/ledger/verify.py`: `Verifier.verify(scope, actor) -> Report`, with records in chain order per use case and the checks of contracts/verification.md. The binding check reads the bound terminal's stored artifact content. Each verification is recorded in `ledger.verification_run`, inside `tracing.span("ledger", "verify")`. This makes T025 and T026 pass.
- [ ] T029 [US4] Implement `src/adlc/ledger/cli.py` (Typer: `verify`, with the actor `cli:<os user>`) and `LedgerService.verify(actor, scope)` (T027)

**Checkpoint**: the evidence is provably intact.

---

## Phase 7: User Story 5 – Evidence and activity can be read per run (P2)

**Goal**: views for 007 and 013, and checklist results.

**Independent test**: after a lifecycle with one rework and one clarification, the run timeline lists every step with durations, and the use-case summary shows one rework, one clarification, and the time split.

### Tests first

- [ ] T030 [P] [US5] Write failing integration tests in `tests/integration/ledger/test_views.py`:
  - US5/AC1: `run_timeline(run_id)` lists activity steps in order, with durations.
  - US5/AC2: `run_checks(run_id)` lists prerequisite and control decisions per attempt (from `run.policy_decision`), plus `checklist_results(run_id)`.
  - US5/AC3: `usecase_summary(usecase_id)` gives per terminal the counts of runs, reworks, clarification rounds and escalations, with `automatic_seconds` and `waiting_seconds`; an open run counts to now.
  - Checklist rows are written once per review with scores and findings.

### Implementation

- [ ] T031 [US5] Write `run.checklist_result` rows (attempt = `auto_retries + 1` at review time, as for agent versions) when `StoreRecommendation` is applied, in `src/adlc/orchestration/engine.py` through `src/adlc/ledger/store.py`, on the same connection
- [ ] T032 [US5] Implement `src/adlc/ledger/views.py` (typed queries over `run.v_run_step`, `run.v_usecase_terminal_summary`, `run.policy_decision`, `run.checklist_result`, `run.artifact_version` and `ledger.ledger_record`) and expose `run_view(run_id)` and `usecase_summary(usecase_id)` on `LedgerService` (T030)

**Checkpoint**: all stories pass.

---

## Phase 8: Polish and cross-cutting

- [ ] T033 [P] Extend `tests/unit/test_no_hardcoded_values.py` so `src/adlc/ledger/` is also checked for route destination names (the existing scans already cover terminal ids, event names and role ids across `src/adlc`)
- [ ] T034 [P] Write `src/adlc/ledger/README.md` (store, versions, profile, record version 2, verification, views, how 007 calls the service, the S3 swap point, and the rule that 007 serves stored files as downloads only, never inline, FR-012) and add a "Backups" note to `deploy/README.md` (create it if absent): the `adlc-files` volume is backed up with the database
- [ ] T035 Run the 003 and 004 scenario suites with the ledger (SC-008), 10 times in a row, and record the result
- [ ] T036 Run `make check` and fix any failure, including the 80% core coverage gate that now includes `ledger/`
- [ ] T037 Run the live-stack check (quickstart §5): rebuild with `make up`, run `scripts.demo_drive`, then `docker compose … exec orchestrator adlc-ledger verify --usecase <id>`. The result must be verified, and the verification run recorded.

---

## Dependencies and execution order

- **Phase 1 → Phase 2 → stories.**
- **US1** (version-2 record) comes first.
- **US2** builds on US1: the record lists versions.
- **US3** depends on US1 (the profile version in the record) but not on US2.
- **US4** depends on US1 and US2 (artifact and attachment checks). It can start after US2, in parallel with US3.
- **US5** depends only on Phase 2 and 003 data, so it can run any time after US1.
- **Phase 8** comes last.

## Parallel examples

- **Phase 2**: T006, T007 and T008 together; T009 and T010 together.
- **US2**: T014, T015 and T016 together; T017 alongside T018.
- **US4**: T025, T026 and T027 together.

## Implementation strategy

1. **MVP**: Phases 1–3. Records reference stored content by hash.
2. **Versions and the profile**: Phases 4–5.
3. **Verification and views**: Phases 6–7.
4. **Polish**: Phase 8.

Run `make check` and commit at every checkpoint.
