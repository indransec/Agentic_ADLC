# adlc.engagement

The engagement layer (feature 016; SA §22.3): a tracker board (the ADO simulator of feature 015,
later Azure DevOps) as a way to drive the lifecycle the inbox drives today. The platform stays the
only source of truth; the board is a view and an input channel. Specification:
`specs/016-engagement-layer/`.

**What it does not do.** It decides nothing: every board change becomes the same
`OrchestratorService` call the inbox makes, as the board user's mapped account, and the platform's
rules accept or refuse it. It names nothing on the board: every type, state, column, field and
decision value comes from `adlc-specs/tracker_mapping.yaml` (a scan in
`tests/unit/test_no_hardcoded_values.py` keeps it so).

## Modules

| Module | Purpose |
| --- | --- |
| `model.py`, `port.py` | Board-neutral types and the `BoardAdapter` protocol with its errors |
| `ado.py` | The ADO REST 7.1 adapter (the only module that knows ADO's shapes or imports `httpx`) |
| `fake.py` | `FakeBoard`: an in-memory board with the same port, for tests |
| `mapping.py` | Loads and schema-checks the tracker mapping; checks it against a board's process |
| `identities.py` | Board user ↔ account (the accounts file's `board_identity`), roles from the account |
| `desired.py` | Pure: the desired board items of one use case (and the snapshot it is built from) |
| `projector.py` | Platform → board: dirty use cases, create and update items, retries, dead letters |
| `classify.py` | Pure: what one board update asks for |
| `inputs.py` | Pure: decision inputs from fields and comment lines; numbered clarification answers |
| `inbound.py` | Board → platform: poll, claim, apply through `OrchestratorService`, reply, recover |
| `reconcile.py` | Make the board match the platform on demand, with a report |
| `health.py` | Sync health from the sync tables (counts and times only) |
| `store.py` | All SQL of the `board_*` and `inbound_*` tables |
| `wiring.py` | Builds all of the above from `BoardSettings` (the API reuses its services) |
| `worker.py`, `cli.py` | The `adlc-board` process (`run`) and its operator commands |

## A change, platform to board

1. A run changes, a clarification is asked, a use case is submitted: a row is added to
   `run_transition`, `run_activity` or `usecase` (append-only, in commit order).
2. `Projector.scan` finds the use cases with rows after its cursor and marks them dirty.
3. `Projector.deliver` computes the use case's desired items (`desired.py`), creates missing
   ones (parents first) and writes the platform-written fields that differ, with the board's
   revision check. A board failure is retried on the outbox's schedule (10 s, 1 min, 5 min,
   15 min) and dead-lettered on the fifth; the CoE requeues it.

The platform never waits for the board: no board call is made inside a platform transaction.

## A change, board to platform

1. `InboundSync.poll` asks the board for items changed at or after the watermark (the board's
   own `asOf` from the previous poll) and reads each item's updates not yet read.
2. Each update is claimed (`inbound_change`) before anything happens; `classify` says what it
   asks for: register a use case, decide, answer, a platform-written field changed, or nothing.
3. The changer is mapped to an account (unmapped: refused). The decision and its inputs are read
   as of that revision (`inputs.py`) and applied through `OrchestratorService` with the update as
   `source`, recorded in the run activity.
4. The outcome is recorded (`inbound_outcome`) and the board answered: accepted (comment; the
   decision field is cleared for the next approver) or refused (comment with the reason; the
   decision or answer cleared). A person's change to a platform-written field is set back.
5. The watermark moves only when every item of the poll was handled. On start, updates claimed
   before a stop are finished (`recover`): accepted if the platform recorded their `source`,
   applied otherwise. On the very first start, existing board history is marked as read, not
   replayed.

## The mapping

`adlc-specs/tracker_mapping.yaml` (schema `adlc-specs/schema/catalogues/tracker_mapping.schema.json`)
names the board's item types per kind (use case, run, clarification), the Epic's column per
terminal, the item state and sub-stage per run state, the decision field and its values, the
decision inputs (field and comment label), the fields only the platform writes, the area and the
polling interval. `adlc-spec validate` checks it against the terminal specs (V-32..V-36);
`adlc-board check-mapping` checks it against the board.

## Identities

Each account in the accounts file that acts on the board has a `board_identity` (its board unique
name). The board's service account (`ADLC_BOARD_SERVICE_IDENTITY`) is nobody's identity, so the
platform's own writes are never read as requests.

## Health and reconciliation

`adlc-board health` and `GET /board/health` (CoE): last poll and its outcome, watermark age,
pending and dead-lettered deliveries, refusals by reason, reverts, the last reconciliation.
`adlc-board reconcile --as <coe>` and `POST /board/reconciliations` make the board match the
platform (platform-written fields only; a person's unread decision is left alone) and store a
report of every difference.

## Pointing it at real Azure DevOps

Settings only: `ADLC_BOARD_URL=https://dev.azure.com`, `ADLC_BOARD_IDENTITIES_URL=https://vssps.dev.azure.com`,
the organisation, project and a personal access token of a service account, and a mapping whose
types, states and fields exist in that project's process. Before connecting it, run the port
contract suite (`tests/contract/board/`) against that organisation and read
`ado_sim/contract/differences.md` (SA §22.2 fidelity rule).
