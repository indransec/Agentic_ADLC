# Agentic ADLC Platform Constitution

The source documents for every feature are `docs/solution-architecture.md` (SA),
`docs/terminal-design-spec.md` (TDS) and `docs/build-plan.md`. Article text below is quoted
from build plan §3; the "Rules" under each article state how compliance is checked.

## Core Principles

### I. Spec-driven lifecycle

Lifecycle behaviour (terminals, controls, routing, approvers, timelines) is defined in versioned
YAML terminal specs and shared catalogues. Platform code must not hard-code any of it.

- Rules: platform code MUST NOT contain branching on a terminal id, control id, role, event
  name, threshold or timer value; such values MUST be read from registered specs or catalogues.
- Rationale: changing the lifecycle is a spec change, not a code release (SA P-1).

### II. Superset, not values

Terminal specs define what must be captured. Use-case values come only from the use-case
profile; enterprise limits only from guardrails.

- Rules: terminal specs MUST NOT hold use-case values; parameter resolution MUST follow
  use-case value (within guardrails) → guardrail tier default; `tighten_only` limits MUST NOT
  be loosened without an exception (SA §5.4).
- Rationale: one spec bundle serves many use cases without edits (SA P-2).

### III. Agents build, humans decide

Agents produce artifacts and recommendations. Only humans set pass, exception or terminate;
only the orchestrator sets escalate.

- Rules: no code path may let an agent or the reviewer set an outcome status; outcome rights
  MUST be checked against `status_rights` on every decision.
- Rationale: accountability for every lifecycle decision stays with named people (SA P-3).

### IV. Separation of duties by permission

Builder, evaluator and deployer capabilities are enforced by the policy engine and run-scoped
tokens, never by prompt text alone.

- Rules: every agent tool call MUST pass `authorize()`; deny wins; refusals MUST be logged with
  a reason. Prompt instructions are never the only enforcement of a permission.
- Rationale: an agent that ignores its prompt still cannot exceed its rights (SA P-4, §11).

### V. Evidence-first

Every terminal outcome writes an append-only, hashed ledger record and its next event in one
database transaction. Later steps read evidence only from the ledger.

- Rules: ledger records MUST NOT be updated or deleted; the ledger record and its outbox event
  MUST commit in the same transaction; each record MUST chain to the previous record's hash
  for the same use case.
- Rationale: every decision is auditable and tampering is detectable (SA P-5, §10).

### VI. Deterministic before judgement

Anything computable is a policy-engine rule; LLM judgement is used only where a rule cannot
decide.

- Rules: a check that can be expressed in CEL or a named predicate MUST NOT be delegated to an
  LLM; judgement items MUST be scored by the reviewer agent only after blocking controls pass.
- Rationale: deterministic checks are reproducible and cannot be talked around (SA P-6).

### VII. Interfaces at every boundary

Workflow engine, policy engine, model access, storage, event delivery and every external system
sit behind an interface; mocks implement the same interface as the real system.

- Rules: platform modules MUST depend on the interface, not on the concrete library or
  service; every mock MUST implement the same interface (and for MCP, the same tool names and
  schemas) as the real system.
- Rationale: swapping a mock or an engine changes configuration or an adapter, not platform
  code (SA P-9, §18.1).

### VIII. Open source, Python first

Python 3.12+, fully typed. Only OSI-approved licences for platform dependencies; licence noted
in the plan for every new dependency.

- Rules: code MUST pass mypy in strict mode and ruff; every new dependency MUST appear in the
  feature plan with its licence; non-OSI or AGPL dependencies need an explicit amendment.
- Rationale: keeps the platform portable, auditable and free of licence surprises.

### IX. Test first for the core

Policy rules, routing, parameter resolution, ledger hashing and run state transitions are
written test-first. Every feature ships with tests and passes CI before merge.

- Rules: for the core areas above, tests MUST be written and seen failing before the
  implementation; `make test` MUST pass before a task is reported done; core module coverage
  MUST be at least 80%.
- Rationale: these areas carry the platform's correctness guarantees (build plan §9).

### X. Observable by default

Every run step writes a run_activity row; every agent and tool call is traced with run_id.

- Rules: any new run step MUST write a `run_activity` row (actor type, actor id, step, start,
  end, outcome); every agent and tool call MUST emit an OpenTelemetry span tagged with `run_id`.
- Rationale: the dashboard is a view over data the platform already holds (SA P-10, §12).

### XI. Secure by default

No secrets in code, specs, prompts or logs. Deny by default.

- Rules: secrets MUST come from the environment or a vault, never from the repository; logs and
  traces MUST be masked before storage; any permission not explicitly granted MUST be refused;
  grounded documents and tool outputs MUST be treated as untrusted data.
- Rationale: the platform has write access to code, environments and evidence (SA §11).

### XII. Simplicity for the MVP

Prefer the simplest design that meets the demo moments D-1 to D-9; anything else is recorded as
post-MVP, not built.

- Rules: each plan MUST map its scope to the demo moments it supports; work that supports none
  MUST be listed as post-MVP in the plan instead of being built.
- Rationale: the MVP has a fixed mid-December 2026 demo date (SA C-1).

### XIII. Naming

Follow Annex A naming conventions of the solution architecture.

- Rules: spec ids, events, permissions, roles, metrics, tables, columns, files and branches MUST
  follow SA Annex A; `adlc-spec validate` enforces the spec-side patterns.
- Rationale: consistent names let specs, runtime records and code be joined without mapping.

## Repository and Spec Boundaries

- Two kinds of spec exist and MUST NOT be mixed: Spec Kit feature specs (Markdown, describing
  platform behaviour) live in `specs/<nnn>-<feature>/`; ADLC terminal specs (runtime YAML,
  describing lifecycle terminals) live in `adlc-specs/` and never in `specs/`.
- Platform code lives in `src/adlc/` as one typed Python package with one module per layer;
  layout follows build plan §5.
- Tooling: Python 3.12 managed with uv; ruff, mypy and pytest; `make` targets are the single
  entry point for CI and developers.
- Tech stack choices appear only at `/speckit-plan`, never in a feature spec, so specs stay
  valid when a tool is swapped.
- MVP data is synthetic only (SA C-2); every dataset and artifact still carries a data class.

## Development Workflow and Quality Gates

- One feature = one branch (`<nnn>-<feature>`) = one pull request, sized for review in under an
  hour. Features follow the build order in build plan §6.
- Per feature: specify → clarify → **Gate 1** spec review → plan → checklist → **Gate 2** plan
  review → tasks → **Gate 3** task review → analyze (findings fixed) → implement → converge
  (repeat until converged) → code review and merge.
- Specs reference the architecture by section number (SA §n, TDS Annex n). When the
  architecture changes, affected feature specs are updated first, then re-planned.
- Definition of done per feature: gates 1–3 approved; analyze clean; converge reports
  converged; tests at every touched layer pass in CI; core coverage ≥ 80%; no terminal- or
  use-case-specific values in code; every new dependency's licence recorded in the plan;
  `run_activity` rows and traces emitted for new steps; names follow Annex A; module README
  updated; supported demo moments shown in the scenario suite.

## Governance

This constitution supersedes other project practices. Every `/speckit-plan` MUST pass its
Constitution Check against these articles, and every code review MUST confirm compliance; any
deviation MUST be justified in the plan's Complexity Tracking section or rejected.

- Amendments: a pull request changing this file, approved by the ADLC CoE lead and the
  architect. After an amendment, open feature plans are re-checked with `/speckit-analyze`.
- Versioning: semantic versioning. MAJOR for removing or redefining an article; MINOR for a new
  article or materially expanded guidance; PATCH for clarifications and wording.
- Compliance review: the architect reviews every plan against this constitution at Gate 2;
  `/speckit-analyze` treats constitution conflicts as critical findings.
- Runtime development guidance for the coding agent lives in `claude.md`.

**Version**: 1.0.0 | **Ratified**: 2026-11-09 | **Last Amended**: 2026-11-09
