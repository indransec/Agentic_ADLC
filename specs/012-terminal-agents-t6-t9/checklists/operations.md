# Operations Requirements Quality Checklist: Terminal Agents T6–T9

**Purpose**: Gate 2 review of release, deployment, operation and evolution requirements.
**Created**: 2026-11-12
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md)

**Review Ownership**: reviewer-owned; `[x]` = criterion satisfied for requirements quality.

- [ ] CHK001 Is the evidence chain T6 checks (statuses, signers, waivers, bound hashes) fully specified from records? [Completeness, Spec §FR-004]
- [ ] CHK002 Are T7's stage steps, success criteria, rollback rule and "not measured" handling unambiguous? [Clarity, Spec §FR-005, research R-06]
- [ ] CHK003 Is the monitor evaluator's timing, episode rule and unevaluable-threshold behaviour defined? [Clarity, research R-02]
- [ ] CHK004 Are agent-proposed events and their confirmation by a person specified (who, how, recorded)? [Completeness, Spec §FR-007]
- [ ] CHK005 Is the change-approval role taken from spec content, and the decision append-only? [Consistency, research R-05]
- [ ] CHK006 Are `telemetry`, `change`, `release`, `retirement` fields and their sources defined? [Clarity, contracts/telemetry-evidence.md]
- [ ] CHK007 Are T9's classification and retire-mode actions traceable to controls? [Coverage, Spec §FR-008, §FR-009]
- [ ] CHK008 Are signed records (release authorisation, handover acceptance) excluded from agents? [Consistency, Spec §FR-002]
- [ ] CHK009 Is the replay scope (through T9 re-entry) measurable and offline? [Measurability, Spec §SC-005]
- [ ] CHK010 Are spec and catalogue version changes listed and the earlier suites required on CI? [Dependency, Spec §SC-007]
