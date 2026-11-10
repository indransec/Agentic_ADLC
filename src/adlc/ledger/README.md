# adlc.ledger

The evidence ledger (feature 005; SA §10). It stores what every terminal run produced, records
who produced each version, keeps the use-case profile, and proves that none of it changed.
Specification: `specs/005-evidence-ledger/`.

## Modules

| Module | Purpose |
| --- | --- |
| `storage.py` | Content store. Structured content goes in `ledger.content_blob`, keyed by `sha256` of its normalised JSON. Files go in a `FileStore` on disk, `<root>/<aa>/<bb>/<hex>`, written to a temp file and renamed. Each file is checked for size, type and content before storing; Office files with macros are refused. |
| `store.py` | SQL for blobs, file objects, artifact versions, attachments and checklist results. |
| `artifacts.py` | Artifact versions: `record` writes a version when content changes, or when attachments are added; `ledger_entries` gives a record's artifact list; `enrich_emitted` adds version and hash to emitted references. |
| `spreadsheet.py` | Reads an uploaded `.xlsx` into rows for a table artifact. |
| `content.py` | Ledger record content version 2 (`build_v2`) and `record_hash`. |
| `binding.py` | `resolve_bound_to`: the package hash a record is bound to. The policy evidence provider uses the same rule. |
| `profile.py` | Versioned use-case profile, and `SqlProfileSource` (004's `ProfileSource`). |
| `verify.py` | `check_chain` (pure checks) and `Verifier` (reads records and content, records each run). |
| `views.py` | Run timeline, checks per attempt, checklist results, artifact versions, ledger reference, use-case summary. |
| `service.py` | `LedgerService`: the operations feature 007 exposes. |
| `cli.py` | `adlc-ledger verify [--usecase UC-nnnn] [--json]`. |

## How runs write to the ledger

The orchestration engine (feature 003) writes on the run's own transaction:

1. **Agent results and escalation completion** become artifact versions (`StoreArtifacts`).
   - An agent version records the attempt, `auto_retries + 1`.
   - A version is written only when the content changed.
2. **The review step** writes one checklist result per scored item (`StoreRecommendation`).
   - A finding written as `"<item>: text"` is stored on that item.
   - Any other finding is stored on an item called `general`.
3. **Closing a run** writes a version-2 record that contains:
   - each artifact's id, version, content hash, producer and attachments;
   - emitted references, including their versions and hashes;
   - the profile version the run opened with;
   - `bound_to`.

   With `pass` or `exception` and emitted values, closing also writes the next profile version.
4. **Opening a run** records the current profile version. The run reads that version until it
   closes.

Records written before feature 005 (content version 1) stay valid. They are verified by hash and
chain only.

## Person edits (`LedgerService`)

An edit has two steps.

1. **Commit the new version.** The `artifact_edited` signal commits the person's new version with
   any uploads.
   - The state does not change.
   - Earlier pass approvals stop counting (`approvals_after_sign_off_id`).
   - A pending waiver is withdrawn: status `rejected`, comment `withdrawn: artifact edited`.
   - The run version goes up, so a decision made on the old content is stale.
2. **Re-run the controls.** The automated controls run on the committed content. The
   `controls_rechecked` signal stores their results.

Who may edit: a person who holds one of the terminal's sign-off roles, required conditional roles
or accountable roles. Edits are allowed only while the run waits for sign-off or is escalated.

`upload_spreadsheet` reads the rows and keeps the workbook as an attachment. `attach_file`
adds a file to the current content.

## Serving files (rule for feature 007)

Files are served for **download only**:

- send `Content-Disposition: attachment`;
- send the media type that was recorded;
- send `X-Content-Type-Options: nosniff`;
- never display a file inline (FR-012).

## Verification

`Verifier.verify(scope, actor)` checks each use case's records in chain order:

- `content`: each record's hash;
- `chain`: each previous-record link;
- for version-2 records, also `artifact`, `attachment` and `binding`.

A report gives keys, hashes and names, never content. Each call writes one
`ledger.verification_run` row; verifying `all` is one row. The CLI exits 0 when verified, 1 when
it finds breaks, and 2 on a configuration error.

## Swapping the file store

`FileStore` has two operations, `put` and `open`, keyed by content hash. To move files to object
storage (S3 or compatible), implement those two operations and pass the new store to
`LedgerContentStore`. Records and verification stay the same, because they reference content
hashes only.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `ADLC_FILE_STORE_DIR` | `data/files` | Root folder of the file store. In compose, the `adlc-files` volume. |
| `ADLC_ATTACHMENT_MAX` | `25MB` (25,000,000 bytes) | Largest file accepted. |
| `ADLC_ATTACHMENT_TYPES` | 7 types | Media types accepted, as a comma list. |

Back up the `adlc-files` volume together with the database (`deploy/README.md`).
