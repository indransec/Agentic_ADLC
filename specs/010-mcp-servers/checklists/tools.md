# Tools Requirements Quality Checklist: MCP Servers

**Purpose**: Gate 2 review of how well the requirements and design cover:
- access control (scopes, run tokens, bound values);
- records and evidence;
- the pilot boundary;
- determinism of build, evaluation and red-team;
- the enterprise mocks and the spec changes.

**Created**: 2026-11-12
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md) · [contracts/](../contracts/)

**Review Ownership**: This checklist is a reviewer-owned requirements-quality review artifact. Mark an item `[x]` only when the reviewer determines the requirements-quality criterion is satisfied.
**Marker Semantics**: `[x]` means the criterion has been reviewed and satisfied for requirements quality. It does not mean implementation work is complete.

## Access and Binding

- [X] CHK001 Is "authorised twice" specified precisely: what the platform gate checks, what the server checks, and in which order the server's checks fail? [Clarity, Spec §FR-002, contracts/run-token.md]
- [X] CHK002 Are all values the model must not choose listed with their source (branch, authorised hash, candidate hash, environment, use case, run), and is "ignored if sent" stated? [Completeness, Spec §FR-003, research R-03]
- [X] CHK003 Is the token lifetime, signing key handling (environment only, never logged or stored) and clock-skew tolerance defined? [Clarity, research R-02]
- [X] CHK004 Is it defined which scopes each terminal gains (T3 dev, T4/T5 test) and that no terminal can provision prod-sim? [Coverage, Spec §FR-001, data-model]
- [X] CHK005 Is the platform's own evidence read (service token, read scopes only) bounded so it cannot write or deploy? [Edge Case, research R-02, R-12]

## Records and Evidence

- [X] CHK006 Is every outcome of a call (ok, refused at gate, refused at server, failed, timed out, unavailable) required to leave a record with a reason? [Completeness, Spec §FR-004, SC-002]
- [X] CHK007 Is it clear which tool results are evidence, that the platform (not the agent) writes them, and that they are hashed and append-only? [Clarity, research R-04, data-model]
- [X] CHK008 Is the switch from synthetic to real evidence for `env.*` and `template.version` specified, including the fall-back and its label? [Completeness, Spec §FR-009, research R-12]
- [X] CHK009 Are the enterprise mocks' record shapes and ids defined well enough for T6–T9 controls to read them? [Clarity, Spec §FR-022, contracts/tools-mcp.md]

## Pilot Boundary and Security

- [X] CHK010 Is it stated which service crosses the networks, what it may hold (no database role, no model keys) and how that is tested? [Completeness, Spec §FR-006, research R-01]
- [X] CHK011 Are the deploy rules (only the T6 hash, checked twice) and the kill switch release (a person only) unambiguous? [Clarity, Spec §FR-017, §FR-018]
- [X] CHK012 Are masking requirements for telemetry and tool output defined (what is removed, how traces are filtered) and measurable over a traffic run? [Measurability, Spec §FR-005, §FR-019, SC-008]
- [X] CHK013 Are Git safety rules complete (no `main`, fill layout only, size limits, moved branch, no hooks or remotes)? [Coverage, Spec §FR-010, research R-05]
- [X] CHK014 Is tool output from pilot systems treated as untrusted data (labelled, capped) consistently with feature 008? [Consistency, Spec §FR-005, Edge Cases]

## Determinism and Measurement

- [X] CHK015 Are the harness metrics defined generically (scored fields, slices) so no use-case values enter platform code, and is repeatability measurable? [Measurability, Spec §FR-014, SC-004, research R-07]
- [X] CHK016 Is each red-team category's success check defined, with the expected result with and without the leak fault? [Clarity, Spec §FR-015, SC-005, research R-08]
- [X] CHK017 Are CI's checks named and is "same hash as the pilot's own build" testable? [Measurability, Spec §FR-011, SC-003]
- [X] CHK018 Is monitor evaluation timing defined so "fires within 5 minutes" can be met and observed? [Measurability, Spec §FR-020, SC-007, research R-11]

## Scope and Compatibility

- [X] CHK019 Are the build-plan deviations (no Docker SDK or Traefik, no DeepEval or garak/PyRIT) recorded with their reasons? [Consistency, Spec Clarifications, plan]
- [X] CHK020 Are the spec and catalogue version changes (registry 2.0.0, T3–T5 2.0.0) and the unchanged agents catalogue stated, with the 001–009 suites required to pass? [Dependency, research R-13, SC-009]

## Notes

- Mark items `[x]` when satisfied. Fixes go into spec.md, plan.md, research.md or the contracts
  before `/speckit-tasks`.
- `/speckit-implement` reads this checklist's state but does not change it.
