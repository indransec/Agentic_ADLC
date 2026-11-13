# Research: Lifecycle Dashboard (feature 013)

## R-01 One read-only dashboard service

**Decision.** A new package `src/adlc/dashboard/` with a read-only `DashboardService` (journey,
activity, KPIs, portfolio, run timeline) over the platform's records, exposed by session-protected
API routes under `/dashboard`. It writes nothing (dead-letter re-queue stays the 003 service
operation). Queries use the app database role; no new tables or migrations.

**Rejected.** Materialised KPI tables: the MVP volumes (tens of use cases, hundreds of runs) are
computed on read well under the 2 s target (SC-004); a view or cache can come later.

## R-02 Journey arrows from routing causation

**Decision.** Each run's `trigger_event_id` names the routing event that opened it; the event's
`causation_run_id` is the run it came from. An arrow is (from run, to run, kind, cause, actor,
time). Kind from the event type and the two terminals, with no terminal names in code:

| Event | Kind |
| --- | --- |
| `<T>.rework` to the same terminal | rework |
| `<T>.rework` to another terminal | reroute (root cause) |
| `<T>.exception` | exception (waiver id and expiry) |
| `<T>.event.<name>` | event (monitor or confirmed proposal) |
| a pass whose target lies before the source (lower number) | re-entry |
| `<T>.terminate` | terminate |
| any other pass | pass |

The cause is the deciding sign-off's root cause and comment (rework, exception), the monitor id and
measured value (event), or the change class (re-entry). A run without a causation run has no arrow.

## R-03 Lanes from the pinned specs

**Decision.** Lanes are the use case's pinned terminals, ordered by terminal number (spec content,
not code). Continuous terminals show a bar per review period; beyond 20 bars the oldest collapse
into one "earlier periods" bar.

## R-04 Time split from transitions and activity

**Decision.** A run's time is split by its state intervals from `run.run_transition`:
`building` → agent working; `checking` and `reviewing` → reviewer (checks are part of review);
`awaiting_clarification` → waiting for clarification; `awaiting_sign_off` and `escalated` →
waiting for people; `blocked` → blocked. Intervals are wall-clock time; the time scale
(`ADLC_TIME_SCALE`) is shown beside durations.

## R-05 KPI definitions (SA §12.3), computed on read

| KPI | From |
| --- | --- |
| Lifecycle elapsed | use case submitted to closed (or now) |
| Time per terminal, split | R-04 per run, summed per terminal |
| Reworks per terminal by root cause | `run.sign_off` rework decisions, `root_cause` |
| Clarifications per terminal, addressed role | `run.clarification_round` |
| Clarification wait | round asked → answer given |
| First-pass yield | terminals whose first run closed pass or exception / terminals with a closed run |
| Escalations | runs entering `escalated`, with trigger (`escalation_trigger`) |
| Reviewer–human agreement | sign-off decisions equal to the run's recommendation status / decisions with a recommendation |
| Human edit rate | agent artifact versions followed by a person version before the pass / agent artifact versions |
| Control first-time pass rate | blocking control decisions at attempt 1 passed / blocking controls at attempt 1 |
| SLA adherence | closed runs within the spec timeline's expected duration for the tier / closed runs |

Each KPI carries its definition and `null` (shown as "no data") when its denominator is zero.
Portfolio KPIs aggregate the same records across use cases (sums for counts and times, pooled
ratios for rates), filtered by risk tier and status.

## R-06 Live refresh

**Decision.** Streamlit fragments re-run every 10 s (`ADLC_UI_DASHBOARD_REFRESH`, default 10 s;
SC-003 needs 15 s); filters live in session state so a refresh keeps them.

## R-07 Run drill-down

**Decision.** The run timeline lists run activity with durations and, per agent attempt, the model
calls (`run.model_call`: model, tokens, cost, latency) and tool calls (`tools.tool_call`: tool,
outcome, duration). The 007 run page gains a "Timeline" section; nothing else on it changes.

## R-08 Dead-letter administration

**Decision.** The dead-letter list adds the last error, attempts, event type, use case, causation
run and payload (on request), with filters by event type and use case; re-queue keeps the 003
operation and its `dead_letter_action` record, shown as history. CoE role only (the existing
`deadletter_role` rule).

## R-09 Journey drawing

**Decision.** Plotly timeline: y = lanes (terminals), x = time; a bar per run from opened to closed
(or now), coloured by final status (pass, rework, exception, terminate, open); arrows as
annotations from the end of the source bar to the start of the target bar, labelled by kind;
hover shows the cause. Plotly is already allowed by build plan §4 (MIT).
