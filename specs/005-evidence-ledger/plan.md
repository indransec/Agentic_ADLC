# Implementation Plan: Evidence Ledger

**Branch**: `005-evidence-ledger` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-evidence-ledger/spec.md`

## Summary

`src/adlc/ledger/` turns the feature 003 baseline ledger into the full evidence ledger:

- **Content store**: one interface keyed by SHA-256. Structured content goes in an append-only
  database table, written in the closing transaction. Files go in a content-addressed directory
  on a volume. The interface allows an S3-compatible store later.
- **Artifact versions**: every agent build attempt and every human edit is a numbered version.
  Spreadsheet uploads become rows, with the file kept as an attachment.
- **Version-2 ledger record**: it references artifact versions by hash, the profile version, the
  package binding and the chain. Version-1 records written by 003 keep verifying under their
  own rules.
- **Use-case profile**: versions built from emitted values. It is the `ProfileSource` and the
  `profile` evidence source of feature 004.
- **Verification**: the `adlc-ledger verify` command and a service operation. Each run is
  recorded.
- **Read views**: run timelines, checks, checklist results and use-case summaries, for 007 and
  013.

## Technical Context

**Language/Version**: Python 3.12 (existing `adlc` package, uv)

**Primary Dependencies**:

- Already used: SQLAlchemy 2, psycopg 3, Typer, OpenTelemetry
- New: openpyxl (MIT) for reading spreadsheet uploads

**Storage**:

- PostgreSQL. Migration `0005` adds:
  - in `ledger`: `content_blob`, `file_object`, `profile_version` and `verification_run`;
  - in `run`: `artifact_version`, `artifact_attachment` and `checklist_result`;
  - the `profile_version` column on `run.terminal_run`;
  - two read views.
- A file store directory (`ADLC_FILE_STORE_DIR`, a Compose volume).

**Testing**: pytest.

- **Unit**: record content and hashing, content store, spreadsheet parsing, profile merge,
  verification rules.
- **Integration**: atomic close with versions, the tamper cases of SC-003 using the superuser
  connection, profile into parameter resolution, views.
- **Scenarios**: the 003 and 004 suites still pass.

**Target Platform**: library in the orchestrator and API processes; the `adlc-ledger` command
for operators.

**Project Type**: library and CLI inside the platform package.

**Performance Goals**: verify a 10-run use case in under 2 s (SC-007). Close adds at most one
insert per new content hash and per artifact version.

**Constraints**:

- No terminal-specific code (constitution I).
- Every new table is append-only for every identity (FR-004).
- A file write precedes the database commit that references it (FR-007).

**Scale/Scope**: about 10 runs per use case, about 10 artifacts per run, a few attachments per
run; attachments up to 25 MB.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| openpyxl | Read `.xlsx` uploads into rows (read-only, values not formulas) | MIT |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Artifact ids, columns, emitted values and `bound_to` come from the pinned specs; the scan covers `ledger/` | Pass |
| II Superset, not values | Profile values come from approved terminal outputs; guardrails stay in the catalogue | Pass |
| III Agents build, humans decide | Human edits are versions produced by a person; agents never edit records or the profile | Pass |
| IV Separation of duties | Only holders of the run's sign-off or accountable roles may submit edited versions | Pass |
| V Evidence-first | Close writes record, versions and profile in one transaction; records reference content by hash; verification proves integrity | Pass |
| VI Deterministic first | Verification is a deterministic recomputation | Pass |
| VII Interfaces | `ContentStore` (database and file implementations; S3 later), `ProfileSource` (004), `Verifier` | Pass |
| VIII Open source | openpyxl (MIT) | Pass |
| IX Test first | Record content and hashing, profile merge and verification rules are written test-first | Pass |
| X Observable | Spans around store, version, profile and verify; verification runs recorded | Pass |
| XI Secure | Append-only tables; media type allow list and size limit; verification reports never contain artifact content | Pass |
| XII Simplicity | One database, one directory; no signing or write-once storage (out of scope) | Pass |
| XIII Naming | Tables and columns follow Annex A.6 | Pass |

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/005-evidence-ledger/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── record.md          # ledger record content v2 (and v1), hashing, chain, binding
│   ├── storage.md         # ContentStore interface, database and file implementations, limits
│   ├── artifacts.md       # versions, producers, edits, spreadsheet uploads (service operations)
│   ├── profile.md         # profile versions, merge rule, ProfileSource, profile evidence
│   └── verification.md    # checks, report format, CLI, service operation
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/adlc/ledger/
├── __init__.py  README.md
├── content.py       # record content v2 builder; v1 reader; hashing (normalise + SHA-256)
├── storage.py       # ContentStore protocol; SqlContentStore (structured); FileStore (files); limits
├── artifacts.py     # ArtifactVersions: record agent and human versions, current versions, schema check
├── spreadsheet.py   # .xlsx → rows (openpyxl, values only)
├── profile.py       # ProfileVersions: version on close, current, for-run; SqlProfileSource (004)
├── binding.py       # resolve the spec's ledger.bound_to in a use case
├── verify.py        # Verifier: per-record checks, report, verification_run
├── views.py         # run timeline, checks, checklist results, use-case summary (queries over views)
├── service.py       # LedgerService: edit_artifact, upload_spreadsheet, attach_file, verify, read views
├── cli.py           # adlc-ledger verify [--usecase UC-nnnn] [--json]
└── store.py         # SQL for the new tables
db/migrations/versions/0005_evidence_ledger.py
src/adlc/orchestration/engine.py   # close writes v2 records via ledger; StoreArtifacts writes versions;
                                   # open records profile_version; review writes checklist results
src/adlc/policy/evidence.py        # profile source from the run's profile version
tests/unit/ledger/  tests/integration/ledger/
```

**Structure Decision**: the `ledger/` layer from build plan §5. The orchestrator calls it
inside its existing transactions. It never opens its own transaction during a close, so the
record, versions, profile and event still commit together.

## Complexity Tracking

No constitution violations; nothing to justify.
