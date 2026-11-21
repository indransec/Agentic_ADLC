# Research: End-to-End Demo on the Board (020)

Decisions behind [plan.md](plan.md). Each: decision, rationale, alternatives.

## R-01 The change request as a fourth board kind

- **Decision**: `items.change` in the tracker mapping: type `Change Request` (a new type in the
  simulator's seed, states `Awaiting approval`, `Approved`, `Rejected`), parent `run`, fields
  title, description, state, change_id (`Custom.AdlcRunId`, as the clarification's id); states
  `awaiting`, `approved`, `rejected`; decision values `approve_change: Approve change` and
  `reject_change: Reject change`; `platform_written.change`: title, description, state, change_id.
  The run kind refuses the change values and the change kind refuses the run values
  (`unknown_value`, naming the allowed ones).
- **Rationale**: clarification 2026-11-21; a type of its own makes changes visible as such on the
  board and in the backlog; the one decision field holds every decision (2026-11-18).
- **Alternatives**: reusing `Task` (kinds told apart only by the link; confusing on the board).

## R-02 Projecting changes

- **Decision**: the use case snapshot gains each run's change requests (`ChangeService` records
  with that `run_id`: id, state, summary, package hash, who decided); `desired()` adds one change
  item under the run's item: the description gives the summary, the hash, what waits for it and
  who decides (the ITSM owner role); the state follows the record (`new` → awaiting, `approved`,
  `rejected`). The projector is already triggered by the run's events (the run waits on the
  change), and reconciliation walks every desired item, so both cover the new kind.

## R-03 Applying a change decision from the board

- **Decision**: `classify` gives `DECIDE_CHANGE` for a new value in the decision field of a change
  item; the inbound sync applies it with `ChangeService.decide(actor, change_id, approve,
  comment)` (rights, append-only record, waiting runs' controls re-run, feature 012), maps
  `NotAuthorised` → `not_authorised`, `InvalidTransition` → `stale` ("already decided"), records
  `source` as for the other commands, clears the decision field and comments as 016 does.
- **Rationale**: one code path for the decision, whether from the inbox or the board.

## R-04 Mapping validation

- **Decision**: the schema requires `items.change` and `platform_written.change`; V-34's checks
  extend to the change states; the board check (`adlc-board check-mapping`) covers the new type,
  states and fields like the others; the 018 contract test keeps the seed's decision values equal
  to the mapping's (now nine values).

## R-05 The driver acts on the board through the board port

- **Decision**: with the board sync on (`BoardSettings.board_enabled`), the demo driver's human
  actions go through `BoardAdapter` instances acting as each demo person (the ADO adapter with
  that person's personal access token): an Epic created for `submit`; the decision field with
  comment and inputs (fields, or Values lines) for `pass`, `reject`, `exception`,
  `complete_escalation`, the waiver decision and `approve_change`; the clarification's answer
  field for `answer`. Field names and values come from the tracker mapping. The driver finds items
  through 016's links (waiting for the projection) and waits for the platform as in 014.
- **Rationale**: the same port the platform uses (it would work against real ADO with real PATs);
  no page scraping in platform code; every human step is a board change by that person (SC-002).
- **Alternatives**: driving the simulator's pages over HTTP (closest to a presenter, but HTML in
  platform code and simulator-only); platform calls (not on the board).

## R-06 Tokens across a demo reset

- **Decision**: the simulator gains `ado-sim token import <unique_name> --stdin` (registers a given
  token, at least 40 characters, hashed as issued ones; refused for an unknown user). A demo
  tokens file outside the repository (`ADLC_DEMO_BOARD_TOKENS`, YAML: board user → token, created
  with random tokens when missing, mode 600) holds the people's tokens; `make demo-reset` (after
  `make up`) imports the sync's token from `.env` (`ADLC_BOARD_TOKEN`) and every person's token from
  the file, and sets the page passwords from `ADO_SIM_DEMO_PASSWORD` for the presenter. Recorded in
  the simulator's differences (ADO lets nobody choose a token's value).
- **Rationale**: the reset wipes the simulator (compose down -v), and with it every token; `.env`
  stays the source of the sync's token.

## R-07 The new steps

- **Decision**: script actions `board_change` (a person sets a platform-written field on an item:
  role, item kind, field key, value; D-12) and `drift` (the operator sets a platform-written field
  with the service account's token, which the sync reads as its own and leaves; D-13) followed by
  `reconcile` (as the CoE: auto through the engagement layer, presenter: Sync status). New
  expectations: `reverted` (the field is back and the item has the platform's comment) and
  `reconciled` (the last reconciliation corrected the field). `MOMENTS` gains D-12 and D-13.
  The steps are the script's last two (16 and 17, on the main use case's Epic): 014's step
  numbers, `FROM_STEP` and tests stay as they are, and with the sync off the two steps are
  skipped (decided while implementing, replacing "after T1 / before T9"; neither touches an
  agent either way).
- **Change record details**: a change request holds a summary, a risk, a window and a plan (no
  package hash); the board item shows those, the deciding role and who decided.

## R-08 Recorded replies

- **Decision**: the recordings replay in call order per agent; the board changes who acts, not
  what the agents are asked. The auto run checks it; only if a reply no longer fits are the
  affected recordings re-recorded (`adlc-replay record`), with a provenance note.

## R-09 Presenter mode

- **Decision**: for each human step the driver prints the demo user, the item's board address
  (`BoardAdapter.item_url`), the decision value and every input (field label and value, or Values
  lines), and waits as in 014; for `reconcile` it says "Sync status, Reconcile now" in the console.

## Dependencies

None new.
