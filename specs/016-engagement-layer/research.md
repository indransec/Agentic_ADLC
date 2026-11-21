# Research: Engagement Layer (016)

Decisions behind [plan.md](plan.md). Each: decision, rationale, alternatives.

## R-01 Package and boundaries

- **Decision**: a new package `src/adlc/engagement/`. Board-neutral types and the `BoardAdapter`
  protocol in `model.py` and `port.py`; the ADO adapter in `ado.py` (the only module that knows ADO
  paths, JSON Patch, WIQL and field reference names); an in-memory `FakeBoard` in `fake.py` that
  implements the same protocol (constitution VII). Everything else (projector, inbound sync,
  reconciliation) talks to the port and reads names from the mapping.
- **Rationale**: constitution VII and the 2026-11-18 decision (adapter inside the platform, no
  plug-ins). A fake that passes the same contract suite as the real adapter lets every core test
  run in-process and fast.
- **Alternatives**: a plug-in package with entry points (refused 2026-11-18); calling the
  simulator's Python code directly (forbidden: boundary, FR-026).

## R-02 Its own process: `adlc-board`

- **Decision**: inbound polling and outbound projection run in one new process, `adlc-board run`
  (compose service `board`, `deploy/Procfile.local` process `board`). It builds the platform's
  `Services` (as the API does) and calls `OrchestratorService` for every command. With
  `ADLC_BOARD_ENABLED=false` (the default) it starts, reports `disabled` on `/health` and does
  nothing, so `make up --wait` and the inbox are unaffected.
- **Rationale**: every board call is an HTTP round trip that can be slow or fail; inside the
  orchestrator worker it would delay run advancement and timers, and its failures would share one
  health signal. A separate process isolates the board's failure domain, can be stopped without
  touching the lifecycle, and matches the pattern of the other services (knowledge, tools,
  bridge).
- **Alternatives**: inside the orchestrator worker (shared loop and failure domain); inside the
  API process (no request to hang the loop on; a background thread per API worker would run the
  poll more than once).

## R-03 Outbound projection is state-based, with the outbox's retry policy

- **Decision**: the projector computes, for a use case, the **desired board state** (Epic, run
  items, clarification items, each as the set of platform-written field values) from the
  platform's tables, compares it with what it last wrote (a hash per item in `board_link`), and
  writes only the differences. A use case is marked **dirty** when any of its history rows appear
  after the projector's cursor (`run_transition`, `run_activity`, `clarification_round`,
  `clarification_answer`, `waiver`, `usecase`): all are append-only or insert-only with
  increasing ids or times, so the cursor is a plain high-water mark. Dirty use cases are delivered
  oldest first, one at a time. Failures are retried on the outbox's schedule (`RETRY_DELAYS`,
  `MAX_ATTEMPTS` imported from `orchestration/outbox.py`: 10 s, 1 min, 5 min, 15 min, dead letter
  on the fifth failure) and recorded per use case in `board_delivery`; a dead-lettered use case is
  listed in sync health and requeued by the CoE (`adlc-board requeue`, `POST /board/requeue`).
- **Rationale**: the platform's outbox delivers each event **inside** the router's write
  transaction, under SQLite's write lock (`orchestration/outbox.py`). A board HTTP call there would
  hold the lock while the board answers and stop every platform write during an outage. Run state
  changes are also not outbox events (they are `run_transition` rows). Recomputing the whole
  desired state is idempotent and order-free: a missed or repeated trigger cannot leave the board
  wrong, and reconciliation (R-08) is the same computation without the hash shortcut. It meets the
  spec's intent for FR-007 (after commit, ordered per use case, outbox retries and dead letters,
  never blocking the platform) without adding events to every transition.
- **Spec change**: FR-007 named "the platform's existing outbox"; it now reads "the outbox's retry
  schedule and dead-letter rule" (spec updated at Gate 2, flagged for review).
- **Alternatives**: a new outbox event for every transition, delivered by a board subscriber
  (adds an event to every state change, and the HTTP call still runs inside the delivery
  transaction); a second table filled by triggers (hidden coupling in SQL).

## R-04 Inbound sync: polling revisions with the simulator's guarantee

- **Decision**: every `poll_interval` (mapping, default 10 s):
  1. WIQL `SELECT [System.Id] FROM workitems WHERE [System.TeamProject] = @project AND
     [System.ChangedDate] >= '<watermark>' ORDER BY [System.ChangedDate] ASC, [System.Id] ASC`
     with `timePrecision=true`;
  2. for each id, read its updates (`$top`/`$skip` pages) and keep those not yet recorded;
  3. process them in update order per item, items in the order returned;
  4. store the answer's `asOf` as the new watermark only after every returned item was processed.
  **First start** (FR-010a): with no stored watermark, the sync queries once, stores the answer's
  `asOf` as the watermark, and records each returned item's latest update id as already seen
  (`inbound_change` kind `baseline`), so existing history is never replayed against today's runs;
  `ADLC_BOARD_START_FROM` overrides the starting point. Reconciliation then aligns older items.
- **Idempotency key**: (work item id, **update id**). In ADO and the simulator an update on the
  other side of a link keeps the item's `rev` (015 T001), so `rev` alone is not unique; the update
  id is. Updates by the service account are recorded as `own` and skipped.
- **Reading a decision as saved**: the decision, comment and inputs are read from the item
  **as of that revision** (`GET .../revisions/{rev}`), not from its current state (FR-015).
- **Rationale**: 015 research R-06 and SC-002 prove this pattern misses nothing; a watermark from
  the platform's clock or from items read after the query would (015 T044).
- **Alternatives**: webhooks (out of scope, decided 2026-11-15); reading current state only
  (loses intermediate changes, SA §22.3).

## R-05 Classifying a board change (pure)

- **Decision**: one pure function, `classify(change, item, link, mapping) -> list[Action]`, with
  actions:
  - `register_usecase`: a mapped Epic type, no link, created (rev 1) or edited by a person, in the
    mapped area;
  - `decide`: a run item whose decision field changed to a non-empty value;
  - `answer`: a clarification item whose answer field changed to a non-empty value;
  - `revert_platform_fields`: any platform-written field changed by a person;
  - `ignore`: nothing the mapping reads.
  One update can yield a revert and a request (a person moves the Epic and sets a decision): the
  revert is written, the request processed.
- **Rationale**: the rules of FR-013–FR-018 are table-driven and the core of the feature;
  a pure function is test-first and property-testable (constitution IX).

## R-06 Applying commands through the existing services

- **Decision**: each action becomes one call of `OrchestratorService` with an `Actor` built from
  the mapped account (name and roles from the accounts file), exactly the call the API route makes:

  | Action | Call |
  | --- | --- |
  | register_usecase | `submit_usecase(actor, name, intake_text)` |
  | decide pass / rework / exception / terminate | `decide(actor, run_id, status, comment, root_cause, reason, fields, target_terminal, expected_version)` |
  | approve or reject waiver | `decide_waiver(actor, waiver_id, approve, comment)` |
  | complete escalation | `complete_escalation(actor, run_id, {}, expected_version)` |
  | answer | `answer_clarification(actor, clarification_id, answers)` |

  `expected_version` is the run's version read just before the call; a version conflict caused by
  the orchestrator moving the run between the read and the call is retried once, then refused as
  stale. The service's exceptions (`NotAuthorised`, `InvalidDecision`, `InvalidTransition`,
  `AlreadyAnswered`, `StaleRun`, `UnknownRun`) become the refusal reason written back to the
  board.
- **Source of the command (FR-024)**: `OrchestratorService` gains an optional `source` argument
  (`{"board_item": id, "update": n}`) recorded in the run activity's `detail`. No rule changes; the
  inbox passes nothing.
- **Rationale**: FR-014 (no rule re-implemented); the ledger, decision log and activity are written
  by the same code as for the inbox.

## R-07 Exactly once across crashes

- **Decision**: `inbound_change` (append-only) is written **before** the command, in its own
  transaction, with status `claimed`; `inbound_outcome` (append-only) is written after it. On
  start, a claimed change without an outcome is resolved by looking for its `source` in the run
  activity (or, for a registration, a `board_link` to the item): found → the outcome is written as
  `accepted`; not found → the command is applied again. The board side is guarded by the board's
  revision check.
- **Rationale**: the command runs in the service's own transaction, so it cannot share one with
  the claim; the source marker in the platform's own record makes the gap decidable.

## R-08 Reconciliation is the projector without the shortcut

- **Decision**: `reconcile()` reads every linked item from the board, computes the desired state of
  every use case, and for each platform-written field that differs writes the platform's value and
  a difference row; missing items are created and linked. The run is recorded in
  `board_reconciliation` with its differences (append-only). Started by `adlc-board reconcile` or
  `POST /board/reconciliations`, only by the role in `ADLC_DEADLETTER_ROLE` (the CoE role, the same
  setting the dead-letter view uses; no role id in code).
- **Rationale**: one computation for projection and reconciliation means they cannot disagree.

## R-09 Person-input fields: who clears them

- **Decision** (revised during T024): the projector never writes the decision, comment, input or
  answer fields. Inbound sync clears a run item's decision, comment and input fields right after
  the platform accepts the request (with `test /rev`; on a conflict it leaves them, and the next
  poll reads the newer change), and restores them on a refusal (inbound-rules §5).
- **Rationale**: inbound sync has just read the update it clears, so it can never clear a decision
  the poller has not read; the earlier plan (the projector clears once inbound has caught up)
  needed a cross-process ordering check for the same guarantee.

## R-10 Decision inputs (FR-028)

- **Decision**: a pure parser `read_inputs(fields_at_rev, comment, mapping, form) -> Inputs |
  Refusal`. Fields first (`Root Cause`, `Reason`, `Rework Target`, `Values` with `name: value`
  lines); for an input whose field is empty, a comment line `<label>: <value>` (labels from the
  mapping, e.g. `root cause`, `reason`, `rework target`, `value <name>`); the remaining comment
  lines are the comment. A field and a differing comment line: the field wins and the reply says
  so. Values are checked against the run's decision form (root causes, terminals, emitted value
  types) before the service is called, so the refusal names the input; the service still checks
  everything again.
- **Rationale**: the 2026-11-20 answer (all three ways); a pure parser is test-first.

## R-11 Identity mapping

- **Decision**: the accounts file gains an optional `board_identity` per account (the board's
  unique name, compared case-insensitively, unique across accounts). The mapping's
  `identities.match` names that property. An account without it cannot act on the board. The
  service account is the board identity in settings (`ADLC_BOARD_SERVICE_IDENTITY`) and must not be
  any account's `board_identity`.
- **Rationale**: decision of 2026-11-18 (accounts file and `roles.yaml`, no table). The accounts
  file is per environment and outside the repository, so demo users stay out of `adlc-specs`.

## R-12 The tracker mapping and its checks

- **Decision**: `adlc-specs/tracker_mapping.yaml` (`catalogue: tracker_mapping`), schema
  `adlc-specs/schema/catalogues/tracker_mapping.schema.json`, loaded by the spec toolkit as an
  optional top-level file. New L4 rules (V-32…V-36): every terminal has a column; every run state
  has a sub-stage and an item state; every human outcome of every terminal, and the waiver and
  escalation actions, has a decision value; every decision input has a field and a comment label;
  every name is unique. `adlc-board check-mapping` (also run at `adlc-board run` start) checks the
  mapping against the board: types, states, fields and link types exist; the service account
  authenticates; the area exists. The mapping is not pinned per use case: it describes the board,
  not the lifecycle, and reconciliation repairs items after it changes.
- **Rationale**: FR-003, FR-004; constitution I and II.

## R-13 What the board shows (Option A board model)

- **Decision** (data in the mapping, defaults below):
  - Epic per use case: title = use case name; description = intake text; state = the current
    terminal's column (`T0 Intake & Qualification` …), `Closed` or `Removed` (terminated);
    `Custom.AdlcSubStage` = run state label; `Custom.AdlcUseCaseId`; area `Agentic ADLC\Use cases`.
  - Run item (`Feature`) per run, child of the Epic: title `<terminal> run <n>`; state from the run
    state (`New`, `Active`, `Closed`, `Removed`); `Custom.AdlcRunId`; `Custom.AdlcEvidenceLink`
    (`<ADLC_BOARD_EVIDENCE_URL>` + run id); description lists the decision values offered, the
    inputs each needs, root causes and terminals allowed, emitted values, the reviewer's
    recommendation and any pending waiver.
  - Clarification item (`Task`) per round, child of its run item: title `Clarification <n>`;
    description with the numbered questions and the addressed role; state `Active` until
    answered, then `Closed`.
  - Every platform reply (accepted, refused, reverted, cleared) is a comment by the service
    account.
- **Rationale**: SA §22.3 Option A model; the seed already declares Feature and Task with the
  ADLC fields. A clarification under its run item (rather than directly under the Epic) keeps the
  hierarchy Epic → Feature → Task valid in ADO; it is still in the Epic's tree.

## R-14 Simulator seed additions

- **Decision**: `ado_sim/seed/demo.yaml` gains `Custom.AdlcRootCause`, `Custom.AdlcReason`,
  `Custom.AdlcReworkTarget` (string), `Custom.AdlcValues` (plainText) and `Custom.AdlcEvidenceLink`
  (string) on every type. Data only; the 015 fixtures whose expected bodies list fields
  (`work_item_types/*`, `fields/list`) are regenerated and reviewed.
- **Rationale**: FR-028 option 1; the simulator has no hyperlink relation type (015 differences),
  so the evidence link is a field.

## R-15 Settings

- **Decision**: `BoardSettings` (prefix `ADLC_`, fields `board_*`): `board_enabled` (default
  false), `board_url`, `board_identities_url` (default `board_url`), `board_organization`,
  `board_project`, `board_token` (secret, at least 20 characters), `board_service_identity`,
  `board_evidence_url`, `board_mapping_file` (default `adlc-specs/tracker_mapping.yaml`),
  `board_start_from` (optional); plus the database settings. `.env.example`,
  `tests/unit/test_env_example.py` and `docs/run-without-docker.md` follow.
- **Rationale**: settings from the environment only (CLAUDE.md); secrets as `SecretStr`.

## R-16 Contract suite

- **Decision**: `tests/contract/board/` holds one suite parametrised over adapters: `FakeBoard`
  always; the ADO adapter against a simulator started by a session fixture (`uv run --project
  ado_sim ado-sim migrate|seed|token issue|serve` on a free port with a temporary database and key).
  Marked `board_contract`; part of `make test` (CI has `uv`). A second test decodes every success
  body in `ado_sim/contract/fixtures/` with the ADO adapter's readers, so a contract change in the
  simulator breaks the platform's build.
- **Rationale**: FR-025, SA §22.2 (the platform's CI starts the simulator from this repository).

## R-17 Observability

- **Decision**: spans `board.poll`, `board.change`, `board.command`, `board.project`,
  `board.reconcile` with use case, run, work item and update id attributes; one log line per
  command and write with outcome; never field values, comments, answers or tokens (FR-023).
  Health (`GET /board/health`, `adlc-board health`) is computed from the sync tables (FR-022).

## Dependencies and licences

No new dependency: httpx (BSD-3-Clause), pydantic, SQLAlchemy, Alembic, ruamel.yaml and the
OpenTelemetry packages are already locked in the platform; tests use respx (BSD-3-Clause) and
hypothesis (MPL-2.0), already dev dependencies.
