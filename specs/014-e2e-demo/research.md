# Research: End-to-End Demo (feature 014)

## R-01 Demo script as data

**Decision.** `demo/script.yaml` holds the SA §21 steps: number, terminal, the human actions
(role, decision, comment, root cause, fields; answer a clarification; approve a change; approve a
waiver; complete an escalation), faults (`model_swap`), what the step proves (D-n) and the expected
result (state, outcome, arrow). The intake comes from `data/reference_usecases/it-service-desk.yaml`.
The driver is generic platform code (`src/adlc/demo/`, console script `adlc-demo`): it reads the
script and names no terminal or use case.

## R-02 Rehearsed agent replies (clarification 1)

**Decision.** Agent text is replayed, everything else runs for real. Two sources:

- T0–T2 (agents that only write): recordings, as `adlc-replay --recording` (feature 008), with the
  demo's extra replies (the T1 rework after the rejection; the T2 clarification).
- T3–T9 (agents that act through tools): rehearsed reply programs that copy values from the tool
  results in the conversation, as a model would. A static recording cannot do this: package
  hashes, result ids and change ids are produced by the run. These programs are today's test
  scripts (`tests/support/acting_scripts.py`), moved to `demo/rehearsed/` (demo assets, outside
  the platform package) and imported by the tests from there, so the demo and CI use the same
  replies.

`--live` routes every agent to the configured model profile instead. The driver runs its own
worker with this gateway (the stack's orchestrator is stopped for the demo, as for `adlc-replay`).

## R-03 Human steps and faults (clarification 2)

**Decision.** The driver runs in the orchestrator container and talks to a host-side wrapper
(`scripts/demo.py`, `make demo`) over stdin/stdout:

- Presenter mode: at a human step the driver prints what to do, where (the web app page) and as
  which role, then waits until the run's state shows it was done (polling, so the presenter needs
  no keyboard); `--auto` takes the step itself through the service operations.
- Faults: the driver prints `fault model_swap trigger`; the wrapper runs `pilot-fault` in the
  pilot container (operator access, never a platform path) and answers `done`.

## R-04 Data reset (clarification 3)

**Decision.** `make demo-reset`: refuse unless `ADLC_ENV=demo`, confirm, `compose down -v` (platform
and pilot volumes), `make up` (migrate, register specs), load accounts, reset the pilot's fault
and traffic state. The ledger stays append-only: a reset removes the database, it never edits it.

## R-05 D-1, D-6, D-8 and negative scenario tests

**Decision.** Offline scenarios in `tests/scenario/`: D-1 (at every terminal of the reference
replay an agent attempt, a reviewer recommendation and a person's decision are recorded), D-6
(the deployed hash equals T3's candidate, T4's and T5's bound hash and T6's package), D-8 (the
dashboard's journey, activity and KPIs over the replay), negatives (an agent decision is refused;
an unauthorised hash is not deployable; an agent cannot raise its own operational event). The
README maps each D-n to its test.

## R-06 Resilience on the running stack

**Decision.** `scripts/resilience.py` (`make resilience`, demo env only) on the running stack:

1. **Restart mid-run**: submit a use case, kill the orchestrator container while a run is
   building, start it; the run completes once (one closed attempt counted as interrupted, no
   duplicate transitions).
2. **Duplicate delivery**: clear the delivery mark of a processed event with the owner identity;
   the router skips it (one run, `processed_event` once).
3. **Dead letter**: restart the orchestrator with `ADLC_ROUTE_FAULT=<event type>` (honoured only
   when `ADLC_ENV` is `dev` or `demo`; a test hook behind the existing `FaultHook`), wait for the
   dead letter, restart without it, re-queue as the CoE through the API; the event is delivered and
   the re-queue recorded.

## R-07 Traceability report

**Decision.** `adlc-ledger trace <usecase>` (feature 005 CLI): for every sign-off, control
decision, routing event and artifact version, its spec version, actor and evidence hash (artifact
content hash, ledger record hash), any gaps, and the chain verification.

## R-08 Rehearsals

**Decision.** Two `--auto` rehearsals on a reset demo environment; findings and fixes recorded in
`tasks.md` (convergence) and `demo/README.md`.
