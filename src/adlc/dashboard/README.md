# Lifecycle dashboard (feature 013, SA §12)

Read-only views over the records the platform already writes; nothing here writes, and no
lifecycle instrumentation is added. `DashboardService` (`service.py`) serves the `/dashboard` API
routes (`src/adlc/api/routes/dashboard.py`); the web application draws them (`ui/pages/journey.py`,
`activity.py`, `portfolio.py`, the run page's Timeline, Dead letters). Every signed-in person may
read every use case; dead letters are for the CoE role.

## Journey

- **Lanes**: the use case's pinned terminals, ordered by terminal number. A continuous terminal's
  review periods beyond 20 collapse into one bar.
- **Bars**: one per run, opened to closed (or now), coloured by outcome, with the current owner:
  the agent while building, the reviewer while checking or reviewing, the addressed role while
  awaiting clarification, the roles still needed at sign-off, the accountable roles when escalated
  or blocked.
- **Arrows** from each run's triggering event to the run it came from (`causation_run_id`; for an
  operational event raised between periods, the run in its payload or the terminal's latest run).
  The event type decides the kind first; only a pass to an earlier terminal is a re-entry.

| Kind | Event | Cause shown |
| --- | --- | --- |
| rework | `<T>.rework[.<root cause>]` to the same terminal | root cause, comment |
| reroute | the same, to another terminal | root cause, comment |
| exception | `<T>.exception` | waiver id and expiry |
| event | `<T>.event.<name>` | monitor, signal, measured values (or the confirmed proposal) |
| re-entry | `<T>.reentry.<terminal>`, or a pass to an earlier terminal | decision |
| terminate, escalate, pass | the event of that name | decision |

## Time split

From each run's state transitions (engine clock, wall time): `building` = agent; `checking`,
`reviewing` = reviewer; `awaiting_clarification` = clarification; `awaiting_sign_off`,
`escalated` = people; `blocked` = blocked; `opened` = other. The API reports the time scale.

## KPIs (SA §12.3)

`kpis.py` holds the formulas; each KPI has its definition, and `null` ("no data") when nothing is
measured, never zero. Lifecycle elapsed; time per terminal (split); reworks per terminal by root
cause; clarifications per terminal by role; clarification wait (answered rounds); first-pass yield;
escalations with trigger; reviewer–human agreement (an `escalate` recommendation is not counted);
human edit rate; control first-time pass rate (blocking controls at attempt 1); SLA adherence
(the spec timeline's expected duration for the tier). The portfolio pools the same records across
use cases: counts and times summed, rates pooled, elapsed the mean per use case.

## Settings

`ADLC_UI_DASHBOARD_REFRESH` (web application, default `10s`): how often the views refresh.
`ADLC_TIME_SCALE` (API): shown beside durations.
