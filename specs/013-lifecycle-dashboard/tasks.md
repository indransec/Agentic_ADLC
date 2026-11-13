# Tasks: Lifecycle Dashboard

**Input**: Design documents from `specs/013-lifecycle-dashboard/` (spec, plan, research, data-model,
contracts, quickstart)

**Tests**: TDD for the computations (constitution IX): arrow kinds, time split, every KPI formula
and portfolio pooling are tested first on fixed records. CI runs `make check`; the relevant suites
run locally while working.

**Format**: `[ID] [P?] [Story] Description` — `[P]` = different files, no dependency on an
unfinished task.

---

## Phase 1: Setup

- [ ] T001 `plotly` (UI only) in `pyproject.toml` and the lock; `ADLC_UI_DASHBOARD_REFRESH` (default `10s`) in the UI settings (`src/adlc/config/settings.py`), `.env.example` and `deploy/compose.yaml`; package skeleton `src/adlc/dashboard/__init__.py` with a README stub.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [ ] T002 [P] `tests/unit/dashboard/test_timesplit.py`: state intervals from transitions (research R-04): `building` → agent; `checking`, `reviewing` → reviewer; `awaiting_clarification` → clarification; `awaiting_sign_off`, `escalated` → people; `blocked` → blocked; an open run's last interval ends at now; a closed run's at its close.
- [ ] T003 [P] `tests/unit/dashboard/test_arrows.py`: arrow kinds per research R-02 from (event type, source terminal, target terminal): rework (same terminal), reroute (another terminal), exception, event, re-entry (target before source), terminate, pass; the event type decides first, so a rework reroute to an earlier terminal is a reroute, never a re-entry (analysis A1); no causation run → no arrow; terminal order by number (no names).

### Implementation

- [ ] T004 `src/adlc/dashboard/timesplit.py` (pure, from transition rows) and `src/adlc/dashboard/journey.py` (`arrow_kind`, lanes ordered by terminal number from the pinned specs, bars, current owner per state: agent while building, reviewer while checking or reviewing, the addressed role while awaiting clarification, the roles still needed at sign-off, the accountable roles when escalated or blocked).
- [ ] T005 `src/adlc/dashboard/service.py`: `DashboardService(engine, runs)` read-only, with the record queries shared by every view (runs, transitions, routing events with causation, sign-offs, waivers, clarifications) per data-model.md.

**Checkpoint**: arrows, lanes, owners and time split computed from records.

---

## Phase 3: User Story 1 – The journey with reroutes (P1)

- [ ] T006 [P] [US1] `tests/integration/dashboard/test_journey.py`: a scripted walk with a T4 rework routed to T3 (root cause `defect`), a clarification, an escalation, an exception with a waiver, and a drift event re-entering at T2: every run is a bar in its lane; each arrow has its kind, cause (root cause and comment, waiver id and expiry, monitor id and value) and actor; open runs name their current owner; the escalations and exceptions panel lists them; a just-submitted use case shows T0 waiting.
- [ ] T007 [US1] `DashboardService.journey(usecase_id)` per contracts/api-dashboard.md (lanes, arrows, panel, time scale); continuous terminals collapse periods beyond 20 into one bar.
- [ ] T008 [US1] `src/adlc/api/routes/dashboard.py`: `GET /dashboard/usecases/{id}/journey` (session; `404` unknown use case); router registered in `src/adlc/api/app.py`.
- [ ] T009 [US1] `src/adlc/ui/pages/journey.py`: Plotly lanes with bars coloured by outcome and arrows as annotations labelled by kind, hover with the cause; KPI strip; escalations and exceptions panel; refresh every `ADLC_UI_DASHBOARD_REFRESH` keeping the selection; the Use cases page opens it.

**Checkpoint**: D-8's journey.

---

## Phase 4: User Story 2 – Activity feed (P1)

- [ ] T010 [P] [US2] `tests/integration/dashboard/test_activity.py`: entries newest first with actor type, actor, step, outcome, duration; filters by use case, terminal, actor type and step; limit default 200, max 1000.
- [ ] T011 [US2] `DashboardService.activity(...)`, `GET /dashboard/activity`, `src/adlc/ui/pages/activity.py` with filters kept across refreshes.

---

## Phase 5: User Story 3 – KPIs (P1)

- [ ] T012 [P] [US3] `tests/unit/dashboard/test_kpis.py`: each of the eleven KPIs (research R-05) on fixed records with hand-computed values: elapsed; time split per terminal; reworks per terminal by root cause; clarifications per terminal with role; clarification wait; first-pass yield; escalations with trigger; reviewer–human agreement; human edit rate; reviewer–human agreement ignores `escalate` recommendations (A4); control first-time pass rate; SLA adherence (expected duration per tier from the spec timeline); a zero denominator gives `null` ("no data").
- [ ] T013 [US3] `src/adlc/dashboard/kpis.py` (pure formulas with id, name, definition, unit) and `DashboardService.kpis(usecase_id)`; `GET /dashboard/usecases/{id}/kpis`.
- [ ] T014 [US3] `tests/integration/dashboard/test_kpis_walk.py`: the scripted walk of T006 gives the hand-computed values (SC-002).

---

## Phase 6: User Story 4 – Run drill-down (P2)

- [ ] T015 [P] [US4] `tests/integration/dashboard/test_run_timeline.py`: a run with an agent build, a tool call, a clarification and a person's edit: activity with durations; per attempt its model calls (model, tokens, cost, latency) and tool calls (tool, outcome, duration).
- [ ] T016 [US4] `DashboardService.run_timeline(run_id)`, `GET /dashboard/runs/{run_id}/timeline`, a "Timeline" section on the 007 run page (`src/adlc/ui/pages/run.py`).

---

## Phase 7: User Story 5 – Dead-letter administration (P2)

- [ ] T017 [P] [US5] `tests/integration/api/test_dead_letters_admin.py`: the list adds attempts, last error, causation run and re-queue history; `GET /dead-letters/{event_id}` returns the payload; both CoE only (`403` otherwise); a re-queue after the fault is fixed delivers the event and is listed in the history.
- [ ] T018 [US5] Extend `src/adlc/orchestration/store.py` (`dead_letters`, `dead_letter`), the routes in `src/adlc/api/routes/requests.py`, and `src/adlc/ui/pages/dead_letters.py` (filters by event type and use case; payload on request; history).

---

## Phase 8: User Story 6 – Portfolio KPIs (P2)

- [ ] T019 [P] [US6] `tests/unit/dashboard/test_portfolio.py`: sums for counts and times, pooled ratios for rates (not means of ratios), filters by risk tier and status; and an integration case with three walked use cases.
- [ ] T020 [US6] `DashboardService.portfolio(risk_tier, status)`, `GET /dashboard/portfolio`, `src/adlc/ui/pages/portfolio.py`.

---

## Phase 9: Polish & cross-cutting

- [ ] T021 [P] `tests/integration/dashboard/test_reference_journey.py`: after the 012 reference replay to T9, every reroute, the T5 exception and the T9 drift re-entry are arrows with their causes (SC-001).
- [ ] T022 [P] Access and performance: every `/dashboard` route `401` without a session (SC-005); a role with no part in a use case reads its journey, activity and KPIs (FR-009, analysis A2); a use case with 50 runs answers its journey in under 2 s (SC-004).
- [ ] T023 [P] UI tests `tests/integration/ui/test_dashboard.py` (AppTest through the API): journey renders lanes and arrows, activity filters survive a refresh, KPI strip shows "no data" where undefined, the journey fragment refreshes every `ADLC_UI_DASHBOARD_REFRESH` (SC-003, analysis A3), portfolio, dead letters for the CoE only.
- [ ] T024 [P] Docs: `src/adlc/dashboard/README.md` (views, KPI definitions, arrow kinds), `src/adlc/ui/README.md` pages.
- [ ] T025 Targeted suites locally (unit dashboard, integration dashboard, API, UI); push after the user's approval and let CI run `make check` (SC-006).
