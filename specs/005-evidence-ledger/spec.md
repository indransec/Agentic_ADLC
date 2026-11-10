# Feature Specification: Evidence Ledger

**Feature Branch**: `005-evidence-ledger`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Feature 005 evidence-ledger (build plan §6 row 005; SA §10 data
architecture, FR-07 use-case profile, FR-08 immutable evidence ledger; TDS Annex C.2 runtime
model): the full ledger record with hash chain and verification, a content-addressed artifact
store, artifact versions (agent-produced and human-edited), the versioned use-case profile, and
read views over run activity and evidence."

## Clarifications

### Session 2026-11-10

- Q: Where is artifact content stored, given that some artifacts may be Word, Excel or other
  files? → A: Behind one storage interface, by content hash. Structured content (table rows,
  signed records, references) is kept in the database and written in the same transaction as
  the ledger record. Files (Word, Excel, PDF, diagrams) are attachments to an artifact, kept in
  a content-addressed file store (a volume in the MVP, S3-compatible storage later), with their
  hash, name, media type and size recorded in the ledger. An Excel upload that edits a table
  artifact is parsed into rows, so controls check the real values, and the original file is
  kept as an attachment.
- Q: How is the use-case profile formed? → A: From the values terminals emit. When a terminal
  passes (or closes with an exception), the values its spec says it emits become a new profile
  version in the ledger. Each run records the profile version current when it opened, and
  parameter resolution (feature 004) reads it.
- Q: Who may run a ledger verification? → A: Any signed-in person. Verification is read-only,
  and its result is hashes and pass/fail, not artifact content. Operators can also run it from
  the command line. Every run is recorded with who ran it.

## User Scenarios & Testing *(mandatory)*

The ledger is the platform's memory and its proof (constitution V). Every closed run leaves one
record that cannot be changed. The record names exactly which spec, which artifacts (by content
hash), which decisions and which earlier record it follows, so anyone can later prove that what
was approved is what was used.

### User Story 1 - Every closed run leaves a complete, verifiable record (Priority: P1)

When a terminal run closes, the ledger record holds everything needed to audit it:

- the spec version and its hash;
- the trigger;
- the final status and every decision, with who decided and when;
- the reviewer's recommendation and the control results;
- the clarification rounds and any waiver;
- the use-case profile version the run used;
- for every artifact, its content hash (and the hashes of any attached files);
- the package hash it is bound to (T4–T7);
- the hash of the previous record for the same use case.

The record can never be changed or deleted.

**Why this priority**: SA §10 and FR-08. Every later terminal, the dashboard and any audit rely
on these records.

**Independent Test**: close a T1 run. Its record lists each artifact's content hash, and each
hash resolves to stored content with that exact hash. Its previous-record hash equals T0's
record hash. Any attempt to change the record is refused.

**Acceptance Scenarios**:

1. **Given** a run that closes, **When** its record is written, **Then** it contains every
   element listed above, and it is written in the same transaction as the outcome event.
2. **Given** an artifact in the record, **When** its content hash is looked up, **Then** the
   stored content is returned, and hashing it again gives the same hash.
3. **Given** two records for one use case, **When** the second is written, **Then** its
   previous-record hash is the first record's hash.
4. **Given** a T4, T5, T6 or T7 record, **Then** its `bound_to` value is the T3 candidate
   package hash.
5. **Given** any identity, **When** it tries to change or delete a record or stored content,
   **Then** it is refused.

---

### User Story 2 - Artifacts are stored once and every version is kept (Priority: P1)

Each artifact version is stored by content hash, so identical content is stored once:

- every agent-produced version (each build attempt);
- every human-edited version (an owner correcting a table at sign-off, or completing an
  escalated run).

Each version records who produced it (agent or person), when, from which version it was
derived, and whether it matches the artifact's columns in the spec. Files (Word, Excel, PDF,
diagrams) are attached to an artifact version and stored the same way.

**Why this priority**: FR-07, and the dashboard's "human edit" KPI needs the agent version and
the human version side by side. Features 006 (agents) and 007 (inbox editing) write versions
through this.

**Independent Test**: an agent builds T1 (version 1). An owner edits the KPI table (version 2)
and attaches the source spreadsheet. Both versions are listed, version 2 points to version 1,
and the spreadsheet is retrievable by its hash. The record at close lists version 2.

**Acceptance Scenarios**:

1. **Given** an agent build, **When** its artifacts are stored, **Then** each becomes version
   `k` of that artifact for the run, produced by the agent, with a content hash.
2. **Given** an artifact awaiting sign-off, **When** an authorised person edits it, **Then** a
   new version is stored, produced by that person and derived from the previous version. The
   run's current artifacts are the latest versions.
3. **Given** an edit with exactly the same content as the current version, **Then** no new
   version is created.
4. **Given** a table version whose rows lack a column the spec declares, **Then** it is stored
   with `schema_valid = false` (the automated controls decide whether that blocks).
5. **Given** a file attached to an artifact version, **Then** it is stored once by hash, with
   its name, media type and size, and the ledger record lists it.
6. **Given** an uploaded spreadsheet that edits a table artifact, **Then** its rows become the
   new version's content and the file is kept as an attachment of that version. A spreadsheet
   whose columns do not match is refused with the reason.

---

### User Story 3 - The use-case profile is versioned in the ledger (Priority: P1)

When a terminal closes with `pass` or `exception`, the values its spec says it emits become a
new version of the use-case profile, merged over the previous version. Examples are T1's
thresholds, KPIs and autonomy levels, and T2's token budget. Every run records the profile
version current when it opened. Parameter resolution (feature 004) uses the profile's values.

**Why this priority**: SA §5.1 and FR-07. Without it, guardrail resolution always falls back to
tier defaults, and later terminals cannot tell which targets were approved.

**Independent Test**: pass T0, T1 and T2. The profile has three versions; version 3 holds T1's
thresholds and T2's token budget. A T3 run opened afterwards records profile version 3, and a
profile value within the guardrail is used for `param.*`.

**Acceptance Scenarios**:

1. **Given** a terminal that passes with emitted values, **Then** a new profile version is
   written. It is the previous version's values with the newly emitted ones replacing those of
   the same name, and it records the source run.
2. **Given** a terminal that re-passes after rework, **Then** its newly emitted values supersede
   the earlier ones in a new version. Earlier versions stay readable.
3. **Given** a run that opens, **Then** it records the current profile version, and its policy
   checks read that version, even if a newer version appears while it runs.
4. **Given** a profile value for a guardrail parameter, **Then** parameter resolution
   (feature 004) uses it when it is within the guardrail, and rejects it otherwise.
5. **Given** a use case before any terminal passed, **Then** its profile is empty (version 0).

---

### User Story 4 - Anyone can verify a use case's evidence (Priority: P1)

An auditor or the CoE runs a verification for a use case, or for all use cases. It reports, for
each record:

- whether its content still hashes to its recorded hash;
- whether it links to the previous record;
- whether every artifact and attachment hash resolves to stored content that still hashes the
  same;
- whether its package binding holds.

Any break is reported with its location. A clean ledger reports as verified.

**Why this priority**: tamper-evidence is only useful if someone can check it (SA §11 "evidence
altered after approval").

**Independent Test**: verify a use case after a T0→T8 lifecycle and it is clean. Corrupt one
stored artifact's content outside the platform, as a database superuser would, and verification
names the record, the artifact and the expected versus actual hash.

**Acceptance Scenarios**:

1. **Given** an untouched ledger, **When** it is verified, **Then** every record is reported as
   verified, and the verification itself is recorded with who ran it and the result.
2. **Given** a record whose content was altered by a superuser, **Then** verification reports
   a content hash mismatch for that record.
3. **Given** a missing or altered artifact or attachment, **Then** verification reports which
   record and artifact, and the expected and actual hash.
4. **Given** a broken chain (a record whose previous hash does not match), **Then**
   verification reports where the chain breaks.
5. **Given** a T4–T7 record whose bound package hash differs from T3's, **Then** verification
   reports the binding mismatch.

---

### User Story 5 - Evidence and activity can be read per run (Priority: P2)

The inbox (feature 007) and the dashboard (feature 013) read one consistent view per run:

- its timeline of steps from the activity record, with actor type and duration;
- its prerequisite, control and checklist results;
- its artifact versions;
- its ledger record.

They also read per-use-case summaries: time spent per terminal, agent time versus human waiting
time, reworks, clarifications and escalations.

**Why this priority**: these views are what 007 and 013 build on. Defining them here keeps one
source of truth for KPI numbers.

**Independent Test**: after a lifecycle with one rework and one clarification, the per-run
timeline lists every step in order with durations, and the use-case summary shows one rework,
one clarification, and agent and human time split per terminal.

**Acceptance Scenarios**:

1. **Given** a run, **Then** its timeline lists every activity step in order, with actor type,
   start, end and duration.
2. **Given** a run, **Then** its prerequisite, control and checklist results are listed per
   attempt, with result and reason. Checklist results are recorded from the reviewer's
   recommendation.
3. **Given** a use case, **Then** its summary gives per terminal:
   - the number of runs, reworks, clarification rounds and escalations;
   - time in automatic steps (agent and checks);
   - time waiting for people (clarifications, sign-off, escalation).

### Edge Cases

- **The same content is produced twice** (same artifact rows in two runs, or an identical file
  uploaded twice): it is stored once and referenced twice.
- **A file is larger than the attachment size limit**: it is refused with the limit stated. The
  limit is configurable, with a default of 25 MB.
- **A file is written but the run's transaction fails**: the orphan file is harmless, because
  nothing references it. Verification reports referenced content only.
- **A spreadsheet has several sheets, or extra columns**: the sheet named after the artifact (or
  the only sheet) is used. Extra columns are kept and reported as not in the spec, and a missing
  declared column makes the version `schema_valid = false`.
- **An emitted value is an artifact reference**: the profile stores the artifact's content hash
  and version, not a copy of its rows.
- **A terminal closes with rework or terminate**: no new profile version.
- **Verification runs while runs are closing**: it checks records committed when it started.
- **Records from before this feature** (003 baseline content) are verified with the rules of
  their content version, so old records stay valid.

## Requirements *(mandatory)*

### Functional Requirements

**Ledger record**

- **FR-001**: Closing a run MUST write one ledger record, in the same transaction as the run's
  close and outcome event, containing:
  - ledger key, run, use case, terminal;
  - spec version and spec hash;
  - trigger;
  - final status;
  - decisions with deciders and times;
  - reviewer recommendation;
  - control results;
  - clarification rounds;
  - waiver;
  - emitted values;
  - profile version;
  - for every artifact: id, version, content hash, schema validity, and its attachments
    (hash, name, media type, size);
  - `bound_to`;
  - the previous record's hash;
  - a record content version.
- **FR-002**: A record's content hash MUST be the SHA-256 of its normalised content (as in
  feature 002). Records of one use case MUST form one chain in close order (as in feature 003).
- **FR-003**: `bound_to` MUST be the terminal spec's `evidence.ledger.bound_to` reference,
  resolved in the use case (the T3 candidate package hash for T4–T7), or empty when the spec
  has none.
- **FR-004**: Ledger records, stored content, artifact versions, profile versions and
  verification results MUST be append-only for every identity.

**Artifact store and versions**

- **FR-005**: Artifact content MUST be stored behind one storage interface, keyed by its
  SHA-256 content hash. Identical content MUST be stored once.
- **FR-006**: Structured content (table rows, signed records, references) MUST be stored in the
  database, in the same transaction as the version that refers to it.
- **FR-007**: Files (attachments) MUST be stored in a content-addressed file store whose
  location is configurable. Each attachment is written before the version that refers to it is
  committed. The interface MUST allow an S3-compatible store to replace the file store without
  changes to callers.
- **FR-008**: Every artifact version MUST record:
  - run, artifact id and version number (1, 2, …);
  - content hash;
  - producer (agent with the build attempt, or person);
  - the version it was derived from;
  - schema validity against the spec's declared columns;
  - creation time;
  - its attachments.
- **FR-009**: The run's current artifacts MUST be the latest version of each artifact. The agent
  path (feature 003 build results and escalation completion) MUST write versions through the
  store instead of keeping artifacts only inline.
- **FR-010**: A person holding a sign-off role or the accountable role of the run's terminal
  MUST be able to submit an edited version of an artifact while the run awaits sign-off or is
  escalated. An edit with unchanged content MUST NOT create a version.
- **FR-011**: A spreadsheet upload for a table artifact MUST be converted into rows (the sheet
  named after the artifact, or the only sheet; the header row gives column names). The
  original file MUST be kept as an attachment of the new version. A spreadsheet that cannot be
  read, or has no sheet that fits, MUST be refused with the reason.
- **FR-012**: An attachment larger than the configured limit (default 25 MB) MUST be refused.
  Only media types on a configured allow list (Word, Excel, PDF, PNG, SVG, plain text and
  Markdown by default) MUST be accepted.

**Use-case profile**

- **FR-013**: When a run closes with `pass` or `exception`, its emitted values MUST produce a new
  profile version: the previous version's values with the new ones replacing values of the
  same name, recording the source run. An emitted value that is an artifact MUST be stored as a
  reference (artifact id, version, content hash).
- **FR-014**: Each run MUST record the profile version current when it opened. Its policy checks
  (`profile.*`, and use-case values in parameter resolution) MUST read that version.
- **FR-015**: The profile MUST be the `ProfileSource` for feature 004 parameter resolution. A
  profile value whose name matches a guardrail is the use case's proposed value for it.

**Verification**

- **FR-016**: Verification of one use case, or all, MUST check per record:
  1. that its content hashes to its recorded hash;
  2. that its previous hash matches the prior record of the use case;
  3. that every artifact and attachment hash resolves to stored content that still hashes the
     same;
  4. that its `bound_to` equals T3's package hash where the spec binds it.
- **FR-017**: Each break MUST be reported with the record, the element (artifact, attachment,
  chain, binding), and the expected and actual values.
- **FR-018**: Every verification run MUST be recorded: who, when, scope, records checked, and
  breaks found.
- **FR-019**: Verification MUST be available as a command for operators (`adlc-ledger verify`)
  and as a service operation for features 007 and 013. Any signed-in person may run it; its
  report contains hashes and results, never artifact content.

**Read views**

- **FR-020**: Per run, a read view MUST give:
  - the activity timeline (step, actor type, actor, start, end, duration, outcome);
  - the prerequisite, control and checklist results per attempt;
  - the artifact versions;
  - the ledger record.
- **FR-021**: Checklist results MUST be recorded per checklist item (score, finding) from the
  reviewer's recommendation when the review step completes.
- **FR-022**: Per use case, a summary MUST give per terminal:
  - runs, reworks, clarification rounds and escalations;
  - time in automatic steps;
  - time waiting for people (`awaiting_clarification`, `awaiting_sign_off`, `escalated`).

  These are measured from the run transitions.

**General**

- **FR-023**: No terminal-specific values or branching (constitution I): artifacts, columns,
  emitted values and bindings come from the pinned specs.
- **FR-024**: Records written before this feature (feature 003 baseline content) MUST remain
  verifiable with the rules of their content version.

### Key Entities

- **Ledger record**: the immutable record of one closed run (FR-001). It has a content version
  and links to the previous record.
- **Stored content**: content stored by SHA-256 hash. Structured content (in the database) or a
  file (in the file store), with size and media type.
- **Artifact version**: one version of one artifact in one run. It records:
  - number and content hash;
  - producer (agent attempt, or person);
  - the version it derives from;
  - schema validity;
  - its attachments.
- **Attachment**: a file linked to an artifact version (hash, name, media type, size).
- **Profile version**: numbered per use case. It holds the values, the source run and its
  creation time.
- **Checklist result**: per run and checklist item, the reviewer's score and finding.
- **Verification run**: who, when, scope, records checked, and breaks with locations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of runs closed after this feature have a record that lists every artifact
  with a content hash resolving to stored content with that exact hash.
- **SC-002**: A full T0→T8 lifecycle verifies clean, and records written by feature 003 before
  this feature also verify clean.
- **SC-003**: Each of these tamper cases is detected and located by verification:
  - altered record content;
  - altered artifact content;
  - a missing attachment;
  - a broken chain;
  - a package binding mismatch.
- **SC-004**: The human-edit share can be computed for any run: the number of artifacts with a
  person-produced version, out of all artifacts of the run.
- **SC-005**: After T0–T2 pass, `param.*` for a guardrail with a profile value within the
  guardrail resolves to the profile value in 100% of later runs. A looser profile value is
  rejected in 100% of cases.
- **SC-006**: Identical content stored twice uses one stored copy.
- **SC-007**: Verifying a use case with 10 closed runs takes under 2 seconds.
- **SC-008**: The 003 and 004 scenario suites still pass.

## Assumptions

- In the MVP, the file store is a Docker volume path configured in settings. An S3-compatible
  store comes later behind the same interface (build plan §4).
- The inbox (007) provides the upload and edit screens. This feature provides the service
  operations and storage they call.
- Signing records (FR-08 target state: signatures, WORM storage) is out of scope for the MVP.
  Hashes and append-only storage give tamper-evidence, not prevention against a database
  superuser. Verification is what detects that case.
- The checklist result source until feature 006 is the stub reviewer's recommendation.
- Spreadsheet reading uses the first row as headers and reads cell values, not formulas.
