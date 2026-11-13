# Feature Specification: Lifecycle Dashboard

**Feature Branch**: `013-lifecycle-dashboard`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "Feature 013 lifecycle-dashboard (build plan §6 row 013; SA §12.1–12.3;
demo moment D-8): journey view with reroutes, run detail, activity feed, KPI views and strip,
dead-letter admin. Simplify if late: fewer KPIs (keep reworks, escalations, clarifications, time
split)."

## Clarifications

### Decided before this feature (recorded for context)

- Everything the dashboard shows is already written by the platform (SA §12: run activity, runs,
  sign-offs, control and checklist results, waivers, routing events with causation, agent calls
  and tool calls); the dashboard adds no lifecycle instrumentation.
- The web application (feature 007) calls only the platform API; the dashboard does the same.
- The human inbox (SA §12.2) exists (features 007 and 012).

### Session 2026-11-13

- Q: Which KPIs, and at what scope? → A: All eleven SA §12.3 KPIs per use case (the strip on the
  journey), plus a portfolio page aggregating them across use cases for the CoE.
- Q: How is the journey drawn? → A: A timeline with one lane per terminal (T0–T9), a bar per run
  coloured by its outcome, and arrows for rework, cross-terminal reroutes, exceptions and T9
  re-entry, from the routing events' causation.
- Q: Who sees what? → A: Every signed-in person sees every use case's journey, activity and KPIs
  (internal MVP); dead-letter administration stays with the CoE role.

## User Scenarios & Testing *(mandatory)*

People need to see, at a glance and live, where a use case is in its lifecycle, why it went
backwards, who it is waiting for, and how much time and effort each step costs (D-8).

### User Story 1 – The journey with reroutes (Priority: P1)

A person opens a use case and sees T0–T9: every run per terminal with its status, time and current
owner (agent, reviewer, person), and arrows for rework, cross-terminal reroutes (e.g. a T4 defect
back to T3), exceptions and T9 re-entry; a KPI strip; and a panel of escalations and exceptions.

**Why this priority**: D-8, and it is how D-2 to D-7 are seen in the demo.

**Independent Test**: Walk a use case with a rework, a cross-terminal reroute, an exception and a
T9 re-entry; the journey shows each run and each arrow with its cause.

**Acceptance Scenarios**:

1. **Given** a T4 rework with root cause routed to T3, **When** the journey is open, **Then** an
   arrow from the T4 run to the new T3 run carries the root cause and the deciding person.
2. **Given** an open run, **Then** its current owner is shown (agent building, reviewer, the role
   whose sign-off or answer it waits for).
3. **Given** the use case moves on, **When** the page is open, **Then** it updates without reload
   within the refresh period.

---

### User Story 2 – Activity feed (Priority: P1)

A chronological feed of agent, reviewer, human and orchestrator actions across a use case (or all
use cases), filterable by actor type, terminal and step.

**Independent Test**: After a walk with clarifications and a rework, filtering for people shows
exactly the human actions in order.

---

### User Story 3 – KPIs (Priority: P1)

The SA §12.3 KPIs per use case: lifecycle elapsed time, time per terminal split (agent working,
reviewer, waiting for clarification, waiting for sign-off), reworks per terminal by root cause,
clarifications per terminal with the addressed role, clarification wait time, first-pass yield,
escalations with terminal, run and trigger, reviewer–human agreement, human edit rate, control
first-time pass rate, SLA adherence.

**Independent Test**: For a scripted walk with known reworks, clarifications, escalations, edits
and timer values, every KPI equals the hand-computed value.

---

### User Story 4 – Run detail drill-down (Priority: P2)

From the journey, a run's step timeline (each activity with its duration), artifacts with agent
and human versions, control results, reviewer findings, the decision and comment, timers, and the
agent's model and tool calls with tokens, cost and latency.

**Independent Test**: A run with an agent build, a tool call, a clarification and a human edit
shows each in its timeline with durations.

---

### User Story 6 – Portfolio KPIs (Priority: P2)

The CoE sees the KPIs aggregated across use cases (per terminal and overall), filterable by risk
tier and status, to see where the lifecycle costs most time and rework.

**Independent Test**: With three walked use cases, each portfolio value equals the aggregate of
the per-use-case values.

---

### User Story 5 – Dead-letter administration (Priority: P2)

The CoE sees dead-lettered events with their error, attempts and the run they belong to, filters
them, inspects the payload and re-queues one; the re-queue is recorded.

**Independent Test**: A failing route dead-letters an event; the CoE sees why, re-queues it after
the fault is fixed, and the event is delivered.

### Edge Cases

- A use case with no runs yet (just submitted): the journey shows T0 waiting to open.
- A continuous terminal (T8) with many review periods: one lane, one bar per period, collapsed
  beyond a limit.
- An event whose causation run is unknown: no arrow, listed in the panel.
- KPIs with no data (no reviewer recommendation yet): shown as "no data", never as zero.
- Time scaled for the demo: durations are shown in real (wall) time, with the scale noted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The journey MUST show every run per terminal (status, opened, closed, duration,
  current owner) and every routing arrow derived from the routing events' causation, with its kind
  (rework, reroute, exception, re-entry, terminate) and cause.
- **FR-002**: The journey MUST show a KPI strip and a panel of escalations and exceptions (with
  waiver expiry).
- **FR-003**: The activity feed MUST list run activity chronologically with actor type, actor,
  step, outcome and duration, filterable by use case, terminal, actor type and step.
- **FR-004**: Every SA §12.3 KPI MUST be computed from platform records only, with its definition
  shown; missing data is shown as such.
- **FR-005**: The run detail MUST add a step timeline with durations and the agent's model and
  tool calls (tokens, cost, latency) to the feature 007 run view.
- **FR-006**: Dead-letter administration MUST show each dead letter's error, attempts, event type
  and run, its payload on request, and re-queue it for the CoE role only; re-queues are recorded.
- **FR-007**: The views MUST refresh on their own (live during the demo) without losing filters.
- **FR-008**: Every view MUST be read through the platform API with a session; no terminal or
  use-case names in code (journey lanes come from the pinned specs).
- **FR-009**: Every signed-in person MUST be able to see every use case's journey, activity and
  KPIs; dead-letter administration MUST be limited to the CoE role.
- **FR-010**: A portfolio view MUST aggregate the KPIs across use cases (per terminal and overall),
  filterable by risk tier and status.

### Key Entities

- **Journey**: runs per terminal and arrows (from, to, kind, cause, actor, time).
- **Activity entry**: run activity row with derived duration.
- **KPI value**: name, definition, value or "no data", per terminal where applicable.

## Success Criteria *(mandatory)*

- **SC-001**: For the reference replay (T0–T9), every reroute, exception and re-entry appears as an
  arrow with its cause (100%).
- **SC-002**: Every KPI equals its hand-computed value on the scripted walk (100%).
- **SC-003**: A change in a use case appears on an open journey within 15 seconds.
- **SC-004**: The journey of a use case with 50 runs loads in under 2 seconds locally.
- **SC-005**: No dashboard endpoint answers without a session; dead-letter actions refused to
  everyone but the CoE role.
- **SC-006**: The earlier suites still pass (CI).

## Assumptions

- Streamlit with Plotly charts (build plan §4).
- Platform health (service metrics) stays in Jaeger and logs; the dashboard is lifecycle-only.
