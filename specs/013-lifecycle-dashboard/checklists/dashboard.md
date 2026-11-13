# Dashboard Requirements Quality Checklist: Lifecycle Dashboard

**Purpose**: Gate 2 review of journey, KPI, feed and admin requirements.
**Created**: 2026-11-13
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md)

**Review Ownership**: reviewer-owned; `[x]` = criterion satisfied for requirements quality.

- [x] CHK001 Is every arrow kind defined with its source records and cause? [Clarity, Spec §FR-001, research R-02]
- [x] CHK002 Is "current owner" of an open run defined for every state? [Completeness, Spec §US1/AC2]
- [x] CHK003 Is each of the eleven KPIs defined with numerator, denominator and "no data" rule? [Measurability, Spec §FR-004, research R-05]
- [x] CHK004 Is the time split's mapping from states to categories unambiguous, including blocked and escalated? [Clarity, research R-04]
- [x] CHK005 Are portfolio aggregation rules (sums vs pooled ratios) specified? [Consistency, Spec §FR-010]
- [x] CHK006 Are refresh timing and filter persistence specified and measurable (15 s)? [Measurability, Spec §FR-007, §SC-003]
- [x] CHK007 Are access rules complete (session everywhere; dead letters CoE only)? [Coverage, Spec §FR-009, §SC-005]
- [x] CHK008 Are edge cases covered (no runs, many review periods, unknown causation, scaled time)? [Coverage, Spec §Edge Cases]
- [x] CHK009 Is the performance target defined with its data size (50 runs, 2 s)? [Measurability, Spec §SC-004]
- [x] CHK010 Is it stated that the dashboard writes nothing and adds no lifecycle instrumentation? [Consistency, research R-01]
