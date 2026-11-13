# Implementation Plan: Lifecycle Dashboard

**Branch**: `013-lifecycle-dashboard` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

## Summary

A read-only dashboard over the records the platform already writes (SA §12): a `DashboardService`
computes the journey with arrows from routing causation, the activity feed, all eleven KPIs per use
case and across the portfolio, and a run timeline (research R-01 to R-07); session-protected API
routes expose it; Streamlit pages draw the journey as Plotly lanes with arrows, refreshing every
10 s (R-06, R-09). Dead-letter administration shows errors, attempts and payloads (R-08).

## Technical Context

**Language/Version**: Python 3.12, uv, ruff, mypy strict, pytest.

**Dependencies**: `plotly` (UI only; MIT; build plan §4).

**Storage**: none new (read-only; no migration).

**Testing**: unit (arrow kinds, time split, every KPI formula on fixed records, portfolio pooling,
lane order); integration (service over a scripted walk with known reworks, a cross-terminal
reroute, clarifications, an escalation, an edit, an exception and a T9 re-entry; API session and
role rules; journey of 50 runs under 2 s); UI (AppTest: journey, feed filters, KPI strip,
portfolio, dead letters) through the API. CI runs `make check`.

**Settings**: `ADLC_UI_DASHBOARD_REFRESH` (default `10s`).

**Constraints**: no terminal or use-case names in code; durations in wall time with the scale
shown; KPIs "no data" when undefined.

## Constitution Check

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Lanes, timelines (SLA) and arrows come from pinned specs and records | Pass |
| III Humans decide | Read-only; the only action (re-queue) is the existing CoE operation | Pass |
| V Evidence-first | Every value traces to a platform record; definitions shown | Pass |
| VII Interfaces | UI calls only the API | Pass |
| X Observable | This is the lifecycle observability of SA §12 | Pass |
| XI Secure | Every route needs a session; dead letters CoE-only | Pass |
| XII Simplicity | Computed on read; no new tables | Pass |

**Post-design re-check**: Pass.

## Project Structure

```text
src/adlc/dashboard/__init__.py  service.py  journey.py  kpis.py  timesplit.py
src/adlc/api/routes/dashboard.py
src/adlc/ui/pages/journey.py  activity.py  portfolio.py  (dead_letters.py, run.py, usecases.py extended)
tests/unit/dashboard/  tests/integration/dashboard/  tests/integration/ui/test_dashboard.py
```

## Complexity Tracking

None.
