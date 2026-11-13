# The end-to-end demo (feature 014, SA §21)

The demo walks the Incident Triage use case (`data/reference_usecases/it-service-desk.yaml`)
through T0–T9 on the full stack and shows D-1 to D-9. Everything runs for real (orchestrator,
policy engine, ledger, tools, the pilot, the dashboard) except the agents' text, which is
replayed from rehearsals so the demo is the same every time.

## Contents

| Path | What it is |
| --- | --- |
| `script.yaml` | The steps: who does what at each terminal, the pilot fault, what each step proves and the expected result |
| `recordings/` | Recorded replies of the writing agents (T0–T2), in call order: the demo's T1 first reply has estimated KPI baselines (rejected at step 2), T2 asks a clarification, a second use case uses T0 and T1 for D-4 |
| `rehearsed/` | Reply programs of the acting agents (T3–T9): they call tools and copy hashes, ids and measured values from the results, as a model would (a static recording cannot hold values the run produces). The tests use the same programs |

These are demo assets for one use case: use-case values belong here, never in `src/adlc`. The
driver (`adlc-demo`, `src/adlc/demo/`) is generic and reads the script.

## Running it

```bash
# once, in the demo environment (ADLC_ENV=demo in .env); wipes the platform and pilot data
make demo-reset

make demo-auto        # rehearsal: the driver takes every human step
make demo             # presenter: the driver tells you each human step and waits
make demo-live        # presenter, with the configured models instead of the rehearsed replies
make demo FROM_STEP=9 # resume after a stop (the driver finds the use cases by name)

make trace USECASE=UC-0001   # every decision linked to spec version, actor and hash; the chain
make resilience              # restart mid-run, duplicate delivery, dead letter (demo env only)
```

`make demo*` stops the stack's orchestrator (the driver runs its own worker), runs the driver in
the orchestrator image with `demo/` mounted, applies the pilot faults it asks for with the
operator tool (`pilot-fault` in `pilot-tools`), and starts the orchestrator again at the end. The
report (markdown and JSON, `demo-report/` in the container, printed at the end) lists every step
and D-1 to D-9 with the runs that show them.

## Presenter guide

Keep the web app open on **Journey** (it refreshes every 10 s) and switch to **Inbox** for the
human steps. The driver prints each step and, in presenter mode, what to do and as which role.

| Step | Terminal | You (role) | Shows |
| --- | --- | --- | --- |
| 1 | T0 | business_owner: submit the use case (name as printed), then pass with risk tier low | D-1 |
| 2 | T1 | product_owner: rework, comment on the estimated baselines, root cause requirement | D-2 |
| 3 | T1 | product_owner and business_owner: pass run 2 | D-2 |
| 4 | T2 | the addressed role: answer the retention question; then pass (same run, not rework) | D-9 |
| 5 | T3 | pass: the candidate package and hash | D-1, D-6 |
| 6 | T4 | qa_eval_lead: rework, root cause implementation, defect log: it goes back to T3 | D-3 |
| 7–8 | T3, T4 | pass run 2 of each | D-3 |
| 9 | T5 | security_officer: complete the escalation; exception with the waiver; risk_owner approves it | D-5 |
| 10 | T6 | release_manager: approve the change (Inbox, Change requests); then pass | D-5, D-6 |
| 11 | T7 | pass: canary, full, registered | D-6 |
| 12 | T8 | pass the review; the driver swaps the pilot's model | D-7 |
| 13 | T9 | pass: the drift is a moderate change, re-entry at T2 | D-7, D-8 |
| 14–15 | T0, T1 (second use case) | reject T1 four times: the run escalates | D-4 |

Timings (demo time scale) and recovery: if a step stops, the driver says why and the step to
resume from; fix the cause and run `make demo FROM_STEP=<n>`. A live-model stop can always be
resumed with the rehearsed replies (`make demo FROM_STEP=<n>`).

## Known behaviour

- After an escalation (T5's kill-switch gap) a person completes the run and it goes to sign-off
  without a reviewer recommendation (the orchestrator's design since feature 003); D-1's test
  states this.

## Rehearsal log

| Date | Mode | Result | Duration | Findings |
| --- | --- | --- | --- | --- |
