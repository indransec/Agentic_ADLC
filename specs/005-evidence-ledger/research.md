# Research: Evidence Ledger (005)

## R-01 Content store (clarification 2026-11-10)

- **Decision**: one `ContentStore` protocol with two implementations.
  - **Structured content** (`SqlContentStore`): the JSON value is stored by its 002 normal-form
    hash in `ledger.content_blob` (`content_hash` PK, `body` jsonb, `size`). An insert uses
    `ON CONFLICT DO NOTHING`, so identical content is stored once. It runs on the caller's
    connection, so it commits with the close.
  - **Files** (`FileStore`): bytes are hashed with SHA-256 and written to
    `<root>/<aa>/<bb>/<hash>`. The write goes to a temporary file, then an atomic rename; an
    existing file is kept. A row in `ledger.file_object` (hash, size, media type) is written
    in the caller's transaction. A crash between the file write and the commit leaves an
    unreferenced file, which is harmless.
- **Rationale**: atomic close for what controls read; files kept out of the database.
  S3-compatible storage can implement the same protocol later (`put_file`, `open_file`,
  `exists`).
- **Alternatives**: everything in the database (a poor fit for large binaries); everything in
  files (no transactional close for structured content). Both were discussed with the user.

## R-02 Hashes

- **Decision**: structured content is hashed as `sha256:` plus the SHA-256 hex of
  `normalise(value)` (002), so key order never matters. Files are hashed as `sha256:` plus the
  SHA-256 of their bytes. Record content hashing is unchanged from 003.

## R-03 Ledger record content version 2 (contracts/record.md)

- **Decision**: `content_version: 2`. Compared with 003's version 1:
  - `artifacts` becomes a list of `{id, version, content_hash, schema_valid, producer,
    attachments: [{content_hash, name, media_type, size}]}`, not inline rows;
  - adds `profile_version` and `bound_to`;
  - `emitted` is unchanged, with artifact references as `{artifact, version, content_hash}`.
- **Old records**: version-1 records have no `content_version` key. Verification checks their
  hash and chain only; their inline artifacts are part of the hashed content (FR-024).
- **Writer**: the orchestrator's `_write_ledger` calls `ledger.content.build_v2(...)`, on the
  same connection.

## R-04 Artifact versions

- **Decision**: `run.artifact_version`, with PK `(run_id, artifact_id, version)`.
  - **Agent results** (`StoreArtifacts` from `agent_result`): one version per artifact whose
    content hash differs from the run's current version for that artifact. Producer `agent`,
    with `attempt` = `auto_retries + 1`.
  - **Escalation completion and human edits**: producer `person`.
  - `derived_from_version` is the previous current version.
  - `schema_valid` is true when every row has every declared column. It is false for a table
    that is not a list of mappings.
  - `run.terminal_run.artifacts` stays as the inline cache of current content (003 readers and
    policy evidence), but it is now always written from the latest versions. The record
    references versions by hash.
- **Rationale**: the human-edit KPI (SC-004) needs both producers, and 007 needs version
  history.

## R-05 Human edits and uploads (service operations)

- **Decision**: in `LedgerService` (exposed by 007):
  - `edit_artifact(actor, run_id, artifact_id, rows, attachments=())`;
  - `upload_spreadsheet(actor, run_id, artifact_id, file_bytes, file_name)`;
  - `attach_file(actor, run_id, artifact_id, file_bytes, file_name, media_type)`.
- **Rules**:
  - **State**: the run must be in `awaiting_sign_off` or `escalated`.
  - **Who**: the actor must hold a role of the applicable sign-off rule, or an accountable
    role, of the pinned spec.
  - **No-op edits**: unchanged content gives no version.
  - **Version bump**: the run's `version` is incremented, so a decision based on older content
    becomes stale (003's optimistic check).
  - **Recording**: an activity row `sign_off` with outcome `edited` is written.
- **Spreadsheets**: openpyxl in read-only mode with `data_only=True`.
  - **Sheet**: the sheet named after the artifact, else the only sheet.
  - **Columns**: row 1 gives the names; empty rows are skipped.
  - **Values**: cell values become strings, numbers or booleans; dates become ISO text.
  - **Refusals**: an unreadable file, or no fitting sheet, is refused (`InvalidUpload`).

## R-06 Profile versions

- **Decision**: `ledger.profile_version`, with PK `(usecase_id, version)`, columns
  `profile_values` jsonb (not `values`, an SQL keyword), `source_run_id` and `created_at`;
  append-only.
  - **On close**: a close with `pass` or `exception` and a non-empty `emitted` writes version
    `n+1` = version `n`'s values plus the emitted values, in the same transaction.
  - **On open**: a run records `profile_version` (the current `n`, 0 when none).
  - **`ProfileSource.values`**: reads the run's recorded version. The protocol gains an
    optional `run_id`; without it, it reads the current version.
  - **`profile` evidence source**: the policy engine's `profile` source reads the run's
    version. It is real evidence, so it is not synthetic.
- **Values for parameter resolution**: emitted names that match a guardrail are used as
  proposed values. The emitted value is used as is, or its `value` when it is a mapping.

## R-07 `bound_to`

- **Decision**: reuse 004's logic, moved into `ledger/binding.py` and shared. It follows the
  spec's `evidence.ledger.bound_to` reference (`T3.candidate_package.sha256`) to the latest
  closed run of that terminal, reading the first row's column. The policy evidence provider
  calls the same function.

## R-08 Verification (contracts/verification.md)

- **Decision**: `Verifier.verify(scope)`, where the scope is one use case or all. Records are
  read in `ledger_record_id` order per use case. Checks:
  1. `content_hash == sha256(normalise(content_json))`;
  2. `previous_record_hash` equals the prior record's `content_hash` (null for the first);
  3. for version-2 records, every artifact and attachment hash exists in the store and
     re-hashes to itself (database content re-normalised; files re-read);
  4. for version-2 records with a spec binding, `bound_to` equals the T3 record's package hash
     at that time.

  The report lists breaks `{ledger_key, check, element, expected, actual}`. A row in
  `ledger.verification_run` records actor, scope, start, records checked and breaks.
- **Superuser tampering**: the tests use the superuser connection (`session_replication_role =
  replica` disables the append-only triggers), which mimics an attacker with full database
  rights.

## R-09 Read views

- **Decision**:
  - **`run.v_run_step`**: activity rows with a duration.
  - **`run.v_usecase_terminal_summary`**: per use case and terminal, the counts of runs,
    reworks (`rework_count > 0`), clarification rounds and escalations
    (`escalation_trigger is not null`), plus time in automatic states and time in waiting
    states, computed from `run.run_transition` with window functions.
  - **Functions in `views.py`**: return typed rows; checks come from `run.policy_decision`
    (004), checklist results from `run.checklist_result`.
- **Checklist results**: written when a `review_result` with a recommendation is applied (one
  row per item: score and finding), in the same transaction.

## R-10 Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `ADLC_FILE_STORE_DIR` | `data/files`; the Compose volume `/var/lib/adlc/files` | File store root |
| `ADLC_ATTACHMENT_MAX` | `25MB` | Size limit (parsed as bytes) |
| `ADLC_ATTACHMENT_TYPES` | docx, xlsx, pdf, png, svg, plain text, markdown | Allowed media types (a comma list) |

They are added to `RuntimeSettings` (API and orchestrator) and to the `adlc-ledger` command
settings.
