# Agents Requirements Quality Checklist: Terminal Agents T3–T5

**Purpose**: Gate 2 review of the requirements and design for the acting agents, real evidence,
checked measured values, table imports and the reference replay.

**Created**: 2026-11-12
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md) · [contracts/](../contracts/)

**Review Ownership**: reviewer-owned; `[x]` means the requirements-quality criterion is satisfied,
not that implementation is complete.

## Agents and Tools

- [X] CHK001 Is each agent's tool set defined by its terminal's scopes, with no tool that deploys, changes the split or acts outside its environment? [Completeness, Spec §FR-001, US4]
- [X] CHK002 Are T3's steps (adapt fill, PR, CI until green, dev environment, artifacts) and its failure paths (CI never green, host down) specified? [Coverage, Spec §US1, Edge Cases]
- [X] CHK003 Is it explicit that agents never write statuses, waivers or the T5 attestation? [Clarity, Spec §FR-003]
- [X] CHK004 Are step limits sufficient and stated for the acting agents? [Measurability, research R-02]

## Evidence and Checks

- [X] CHK005 Is each evidence source (`ci`, `sbom`, `harness`, `redteam`, `dlp`) defined with where it comes from, which result is "latest" and the candidate it belongs to? [Clarity, Spec §FR-010, §FR-011, contracts/evidence-sources.md]
- [X] CHK006 Is the comparison rule of `rows_match` (keys, columns, tolerance, missing keys) unambiguous? [Clarity, Spec §FR-012, research R-07]
- [X] CHK007 Are all copied measured values covered by a check (T3 tests and scans, T4 metrics and calibration, T5 RAI)? [Coverage, research R-07]
- [X] CHK008 Is "not measured" handled so a gap fails visibly and can be waived? [Edge Case, Spec Edge Cases]

## Table Import

- [X] CHK009 Does the import contract keep the decision with the agent (which result, which requirement mapping) and the values with the recorded result? [Consistency, research R-08, contracts/artifact-import.md]
- [X] CHK010 Are invalid imports (foreign result, wrong kind, missing mapping) defined as invalid output? [Edge Case, contracts/artifact-import.md]

## CI and Harness

- [X] CHK011 Are the CI checks (tests and coverage, SAST, secret scan, SBOM, observability) and the meaning of `green` specified? [Completeness, Spec §FR-005, contracts/ci-report.md]
- [X] CHK012 Is judge calibration defined (judge, labelled slice, agreement) and honest about synthetic labels? [Clarity, Spec §FR-008, research R-06]
- [X] CHK013 Is the mapping from harness measures to metric-catalogue names stated without use-case values in code? [Consistency, research R-06]

## Rework, Waiver and Replay

- [X] CHK014 Is the rework route from a T4 defect to T3 (root cause) and the T3 rework context specified? [Coverage, Spec §US2, research R-10]
- [X] CHK015 Is the T5 waiver path (reviewer recommends, person decides) traceable to existing features? [Dependency, Spec §US3]
- [X] CHK016 Is the reference replay scope (only the use case that matches the pilot template) justified and measurable? [Assumption, research R-09, Spec §FR-013]

## Compatibility

- [X] CHK017 Are the spec and catalogue version changes listed, with the 001–010 suites required to pass? [Dependency, data-model, Spec §SC-008]
- [X] CHK018 Are the new pilot dependencies and their licences recorded? [Constitution VIII, plan]
