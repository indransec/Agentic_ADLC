# Demo Requirements Quality Checklist: End-to-End Demo

**Purpose**: Gate 2 review of the demo, scenario, resilience and traceability requirements.
**Created**: 2026-11-13
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md)

**Review Ownership**: reviewer-owned; `[x]` = criterion satisfied for requirements quality.

- [x] CHK001 Is every SA §21 step mapped to script actions, an expected result and the D-n it proves? [Completeness, Spec §US1, research R-01]
- [x] CHK002 Is it clear what is replayed (agent text only) and what runs for real? [Clarity, Spec §FR-002, research R-02]
- [x] CHK003 Are presenter-mode waits and `--auto` behaviour defined for every kind of human step? [Completeness, Spec §FR-003]
- [x] CHK004 Are stop-and-resume behaviour and messages defined for a failed step? [Coverage, Spec §US1/AC3]
- [x] CHK005 Is the reset's scope and its guard (demo env, confirmation) unambiguous? [Clarity, Spec §FR-004]
- [x] CHK006 Does each of D-1 to D-9 name its scenario test? [Traceability, Spec §FR-005, §SC-002]
- [x] CHK007 Are the three resilience checks defined with measurable pass conditions? [Measurability, Spec §FR-007, research R-06]
- [x] CHK008 Is the trace report's coverage (record kinds, links, gaps) specified? [Completeness, Spec §FR-008]
- [x] CHK009 Are the negative tests' attempted actions listed? [Coverage, Spec §FR-006]
- [x] CHK010 Is the route-fault knob restricted and documented so it cannot be on in production? [Security, research R-06]
