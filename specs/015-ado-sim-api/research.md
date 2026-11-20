# Research: ADO Simulator API (015)

Each entry: decision, rationale, alternatives considered.

## R-01 Contract source: Microsoft Learn's 7.1 reference, not a vendored specification

- **Decision**: The subset's contract (`ado_sim/contract/openapi.json`) is written by us from
  Microsoft's ADO REST API 7.1 reference pages on Microsoft Learn. Each operation in
  `contracts/operations.md` cites its reference page. No Microsoft file is copied into the
  repository; field reference names, paths and shapes are facts of the public API.
- **Rationale**: Microsoft's machine-readable specifications (`MicrosoftDocs/vsts-rest-api-specs`)
  no longer exist: the repository returns 404 (checked 2026-11-20), and a third-party note confirms
  it was removed ([krateo-blueprints PR #1](https://github.com/krateo-blueprints/azuredevops-provider-kog/pull/1)).
  Microsoft's `azure-devops-rust-api` (MIT), which generated code from them, was archived on
  2026-10-26 and its specification submodule points at the removed repository. The repository
  behind the Learn pages (`MicrosoftDocs/vsts-docs-rest-apis`) is not public. An archived copy
  (Software Heritage) has no licence we can verify, so vendoring it would break constitution VIII.
- **Alternatives**: vendor the Software Heritage copy (licence unverifiable); generate from the
  archived Rust crate's sources (indirect, archived); write the contract from the reference
  (chosen). Clarification Q3's intent (the contract follows Microsoft's published reference) is
  kept; the spec's wording was corrected.

## R-02 Behaviours the reference does not state

The reference pages list only `200 OK` for most operations. Where they are silent, the simulator
follows observed ADO behaviour and lists the choice in `contract/differences.md`:

| Case | Behaviour | Source |
| --- | --- | --- |
| `test /rev` fails | `412 Precondition Failed`, error body `{"$id","innerException","message","typeName","typeKey","errorCode","eventId"}` with the current revision in the message | community reports of ADO behaviour; to confirm against real ADO before a real tracker is connected |
| Unknown field, invalid state, bad patch | `400 Bad Request` with the same error body | ADO error contract |
| Unknown work item | `404 Not Found` | ADO |
| Missing or invalid token | `401 Unauthorized`, no body detail | ADO (PAT auth) |
| Unsupported operation | `404 Not Found` | ADO for unknown routes |
| Revision limit | not enforced (ADO refuses updates after 10,000 revisions, [DevBlogs 2022](https://devblogs.microsoft.com/devops/work-item-revision-limits/)) | listed as a difference |

## R-03 Web framework and process

- **Decision**: FastAPI with uvicorn, in its own uv project `ado_sim/` at the repository root
  (src layout `ado_sim/src/ado_sim/`), the same pinned versions as the platform and the pilot
  (FastAPI 0.162.2, uvicorn 0.54.0, pydantic 2.14.3). Routes use ADO's path shapes
  (`/{organization}/{project}/_apis/wit/...`) and the `api-version` query parameter.
- **Rationale**: already used and pinned in two projects here; the board, backlog and form of 017
  and 018 add server-rendered pages to the same app; the test client exercises the API in-process.
- **Alternatives**: Starlette alone (more hand work for validation and OpenAPI); Flask (a new
  dependency with no gain).

## R-04 Data store

- **Decision**: one SQLite file (`ADO_SIM_DB_PATH`) through the standard library `sqlite3`
  module, no ORM. Write-ahead log, foreign keys on, `BEGIN IMMEDIATE` for every write transaction,
  times as ISO 8601 text in UTC with microseconds. The schema lives in numbered SQL files applied
  in order by `ado-sim migrate` (a `schema_version` table); 015 ships `0001_initial.sql`.
- **Rationale**: the simulator must share no code with the platform (constitution VII), so it
  cannot reuse `adlc.db`; the same proven ideas are reimplemented in about 100 lines. A single
  writer at a time is plenty for a tracker used by a few people and one sync process. No
  SQLAlchemy keeps the dependency list to what the project already uses.
- **Alternatives**: SQLAlchemy Core and Alembic (more machinery than one schema needs); JSON
  files (no transactions, no concurrency control).

## R-05 History model: full revision snapshots plus updates

- **Decision**: every change writes one `update` row (changed fields with old and new values,
  relation changes, changer, time) and one `revision` row (the full field values and relations as
  of that revision); `work_item` holds the current values and revision. All three are written in
  one transaction; `update` and `revision` rows are never changed (triggers refuse UPDATE and
  DELETE, except on reset).
- **Rationale**: `GET .../updates` and `GET .../revisions/{rev}` are both in scope and both must
  be exact (FR-007, FR-008); storing both avoids replaying patches to rebuild a revision, and a
  few thousand items are small.
- **Alternatives**: updates only, rebuilding revisions by replay (slower reads, more code);
  revisions only, diffing to produce updates (old values of relation changes are awkward).

## R-06 Changed dates and "changed since" completeness

- **Decision**: `System.ChangedDate` comes from the simulator's clock with microseconds; if the
  clock would give a time not later than the latest changed date of **any** item, that date plus
  one microsecond is used. Writes are serialised (`BEGIN IMMEDIATE`), so changed dates increase
  strictly in commit order across the database. A WIQL answer's `asOf` is the latest changed date
  in the query's own snapshot (now, if there are no items). A "changed since" query uses `>=`, so
  a reader that passes back the previous answer's `asOf` re-reads that item rather than missing a
  later change in the same instant; readers de-duplicate by (id, rev).
- **Rationale**: FR-009 and SC-002 require that no change is missed between two reads. Every
  change outside a query's snapshot was committed later, so it has a later date than the
  snapshot's `asOf`. Found during T044: per-item ordering was not enough. A bound taken from
  items read after the query, or an `asOf` from the clock, skipped changes stamped before the
  bound but committed after the query (a slow writer); the property test reproduces both.
- **Alternatives**: a global sequence number exposed as a field (not ADO behaviour).

## R-07 JSON Patch

- **Decision**: our own small applier for ADO's patch dialect (`add`, `replace`, `remove`, `test`
  on `/fields/<ref>`, `/relations/-`, `/relations/<index>` and `/rev`), all-or-nothing, inside the
  write transaction; a patch that changes nothing creates no revision.
- **Rationale**: ADO's paths are not plain JSON documents (fields keyed by reference name,
  relations as a list with attributes), so a generic RFC 6902 library would still need the ADO
  mapping; the applier is about 150 lines and fully unit-tested.
- **Alternatives**: `jsonpatch` (BSD; generic semantics, still needs the mapping and validation).

## R-08 WIQL subset

- **Decision**: a hand-written tokenizer and recursive-descent parser for the documented subset
  (`contracts/wiql.md`), compiled to parameterised SQL over the current values; anything else is
  refused with `400` naming the construct. Supported: `SELECT [System.Id] FROM workitems WHERE ...
  ORDER BY ...` with `=`, `<>`, `<`, `<=`, `>`, `>=`, `IN`, `UNDER` (area path), `AND`, `OR`,
  parentheses, `@project`, `@today`; and `FROM workitemLinks` with `MODE (MustContain)` for parent
  and child links. Limit `$top` up to 20,000.
- **Rationale**: only these forms are needed by 016–018; a parser that refuses the rest cannot
  silently return a wrong result (US3 scenario 3).
- **Alternatives**: a parser generator such as Lark (a new dependency for a small grammar);
  regular expressions (fragile, hard to refuse precisely).

## R-09 Personal access tokens

- **Decision**: tokens are 52 random characters (as ADO's) from `secrets`; stored as
  HMAC-SHA256 with a server key (`ADO_SIM_TOKEN_KEY`, at least 32 characters) plus the issue
  time and the identity; issued and revoked only by `ado-sim token issue|revoke|list`. Requests
  authenticate with Basic auth (any user name, the token as password), as ADO PATs do, or
  `Authorization: Bearer <token>`. Comparison is constant time.
- **Rationale**: tokens are long random secrets, so a keyed fast hash is enough (password hashing
  such as argon2 protects low-entropy passwords against guessing, which does not apply); the key
  means a copied data file does not let anyone test tokens offline. No new dependency.
- **Alternatives**: argon2 (`argon2-cffi`, MIT; slower per request, no benefit for random
  tokens); plain sha256 (testable offline if the data file leaks).
- **Gate 2 additions**: tokens do not expire in the MVP (valid until revoked); changing
  `ADO_SIM_TOKEN_KEY` invalidates every token (they must be issued again); unknown, revoked and
  wrong tokens get the same `401` with an empty body (FR-015).

## R-10 Seed file and process

- **Decision**: `ado_sim/seed/demo.yaml` (ruamel.yaml, as the pilot) describes the organisation,
  project, area path tree, the Agile process (types Epic, Feature, User Story, Task, Bug with New,
  Active, Resolved, Closed, Removed; the Epic's states replaced by the terminal stages), the
  custom fields (`Custom.AdlcDecision`, `Custom.AdlcSubStage`, `Custom.AdlcRunId`,
  `Custom.AdlcUseCaseId`, `Custom.AdlcComment`, `Custom.AdlcClarificationAnswer`) and the
  identities (demo users and the platform's service account). `ado-sim seed` loads it into an
  empty database; `ado-sim reset --yes` empties everything and seeds again.
- **Rationale**: the terminal stages and fields are data, never code (CLAUDE.md, constitution
  II); features 016–018 may add fields to the seed without changing the simulator.
- **Alternatives**: process definition through ADO's process API (out of scope, heavy).

## R-11 Contract tests and fixtures

- **Decision**: `ado_sim/contract/fixtures/<operation>/<case>.json` holds a request (method,
  path, query, headers without the token, body) and the expected response (status, and a
  body pattern where ids and times are matched by type, not value). A replay test runs every
  fixture against a freshly seeded simulator with a test token; a second test checks that the
  served OpenAPI document equals the committed `contract/openapi.json` and lists exactly the
  routes the app serves. Feature 016 reuses the fixtures for its adapter tests.
- **Rationale**: SC-001; the adapter is built against the published contract, not the code.

## R-12 Observability and logs

- **Decision**: one log line per request (operation, identity unique name, status, duration);
  never field values, comment text or tokens. OpenTelemetry traces only when `ADO_SIM_OTLP_ENDPOINT`
  is set (project `ado-sim` in Phoenix), with the same libraries and versions as the pilot.
- **Rationale**: FR-024, constitution X and XI.

## R-13 Running it

- **Decision**: `ado-sim serve` (uvicorn) on `ADO_SIM_PORT` (default 8600). Compose: service
  `ado-sim`, image `adlc-ado-sim:0.1.0` from `deploy/ado-sim.Dockerfile`, volume `ado-sim-data`,
  port `${ADO_SIM_PORT:-8600}`, on the platform network (the platform's adapter will call it in
  016). Without Docker: a process in `deploy/Procfile.local`, data in `data/local/ado_sim/`.
  `make ado-sim-check` (ruff, format, mypy, pytest, coverage ≥ 80%) is part of `make check`, as
  `pilot-check` is.
- **Rationale**: same patterns as the pilot and Phoenix; no new infrastructure.

## Dependencies and licences

| Dependency | Version | Licence | Use |
| --- | --- | --- | --- |
| fastapi | 0.162.2 | MIT | API |
| uvicorn | 0.54.0 | BSD-3-Clause | server |
| pydantic | 2.14.3 | MIT | request and response models |
| ruamel.yaml | 0.19.1 | MIT | seed file |
| opentelemetry-api, -sdk, -exporter-otlp-proto-http | 1.45.2 | Apache-2.0 | optional traces |
| httpx | 0.28.1 | BSD-3-Clause | tests (test client) |
| pytest, pytest-cov, ruff, mypy, coverage | as the pilot | MIT / Apache-2.0 | development |

All are already used by the platform or the pilot; no new licence enters the repository.
