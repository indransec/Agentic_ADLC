# Implementation Plan: Policy Engine

**Branch**: `004-policy-engine` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-policy-engine/spec.md`

## Summary

`src/adlc/policy/` is a deterministic policy engine. It implements the feature 003
`PolicyEngine` protocol (`evaluate`, `authorize`).

- **Evaluation**: rules are the CEL expressions in the pinned specs, which feature 002 already
  parses and validates. They run in cel-python with a library of the 60 catalogued predicates.
- **Evidence**: comes through an evidence-provider interface over feature 003's records (runs,
  sign-offs, waivers, ledger content, intake, trigger). Sources built by later features answer
  "not available", unless the synthetic provider supplies them. Decisions that read synthetic
  evidence are labelled.
- **Parameters**: resolved once per run within the guardrails (SA §5.4) and frozen in an
  append-only table.
- **Decision log**: every decision writes one append-only record and a span.
- **Orchestrator wiring**: the orchestrator process switches from `StubPolicy` to the real
  engine. The stub agent reads synthetic, control-passing artifacts from data files.

## Technical Context

**Language/Version**: Python 3.12 (existing `adlc` package, uv)

**Primary Dependencies**: cel-python (already a dependency since 002, Apache-2.0; now used for
evaluation as well as parsing), SQLAlchemy 2, OpenTelemetry. No new dependency.

**Storage**: PostgreSQL. Migration `0004` adds two append-only tables:

- `run.policy_decision`;
- `run.run_parameter_set`.

**Testing**:

- **Unit tests** for every predicate, parameter resolution, authorization matching and
  fail-closed evaluation. They are test-first (constitution IX).
- **Hypothesis property tests**: resolution never loosens a tighten-only limit; deny always
  wins.
- **Integration tests** (testcontainers): the evidence provider over real 003 records,
  append-only decisions, every T0–T9 rule evaluated.
- **Scenario tests**: the 003 suite is re-run with the real engine and synthetic data.

**Target Platform**: in-process library used by the `orchestrator` service (no separate
service in the MVP; SA §9 allows OPA or Cedar later behind the same two calls).

**Project Type**: library inside the platform package.

**Performance Goals**: one control under 50 ms at p95 (SC-008). Achieved with:

- compiled programs cached per expression;
- evidence loaded only for the namespaces an expression references (002 `expressions`);
- a per-run cache of the frozen parameter set.

**Constraints**:

- No terminal-specific code (constitution I); the scan covers `policy/` too.
- Fail closed (constitution XI).
- Expressions have no side effects.

**Scale/Scope**: 98 prerequisite and control expressions in T0–T9, 60 predicates, and 9
guardrails per tier.

### New dependencies and licences (constitution VIII)

None. cel-python (Apache-2.0) was recorded in feature 002.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Rules, column names, terminals and values come from specs and catalogues. Predicates are generic over the arguments they receive. A startup check binds the predicate library exactly to `predicates.yaml`; the no-hard-coded scan covers `policy/` | Pass |
| II Superset, not values | Thresholds come from guardrails and the use-case profile, never from code | Pass |
| III Agents build, humans decide | The engine decides checks, never outcomes. Unevaluable approver conditions require the approver (fail toward more human approval) | Pass |
| IV Separation of duties | `authorize` enforces allow and deny (deny wins, default deny) and run scope, using the spec authorities that 002 validates for duty groups | Pass |
| V Evidence-first | Rules read evidence only from records and the ledger; every decision is logged append-only with its inputs | Pass |
| VI Deterministic first | All prerequisites, controls and conditions are evaluated here, outside models | Pass |
| VII Interfaces | The 003 `PolicyEngine` protocol is implemented as is. New protocols: `EvidenceProvider`, `ProfileSource`, `Directory` | Pass |
| VIII Open source | No new dependency | Pass |
| IX Test first | Predicates, parameter resolution, authorization and fail-closed behaviour are tested first | Pass |
| X Observable | A decision record and a span `adlc.policy.<evaluate\|authorize>` per call, with run id | Pass |
| XI Secure | Fail closed; append-only decisions; synthetic evidence labelled; default deny | Pass |
| XII Simplicity | An in-process library; per-expression program cache; no policy service | Pass |
| XIII Naming | Tables and columns follow Annex A.6 | Pass |

**Interface note**: the 003 `EvalResult` gains an optional `synthetic: bool = False` field.
Existing callers are unchanged, and the orchestrator copies it into the run's control results
(FR-025).

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/004-policy-engine/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── policy-engine.md      # evaluate / authorize behaviour, results, fail-closed table
│   ├── evidence.md           # namespaces, provider interface, terminal evidence shape, synthetic data
│   ├── predicates.md         # the 60 predicates: arguments, semantics, failure reasons
│   └── authorization.md      # pattern grammar, deny-wins, run scope, tool scopes
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/adlc/policy/
├── __init__.py  README.md
├── engine.py          # CelPolicyEngine: evaluate, authorize, decision logging, spans
├── compiler.py        # expression → compiled program cache; references via spec_toolkit.expressions
├── activation.py      # builds the CEL activation from evidence for the referenced namespaces
├── values.py          # JSON ↔ CEL values; numbers-in-text; durations; "not available" marker
├── evidence.py        # EvidenceProvider protocol, SqlEvidenceProvider, Composite, Unavailable
├── synthetic.py       # SyntheticEvidenceProvider + synthetic artifact loader (data files)
├── directory.py       # Directory protocol; account-file directory; unavailable directory
├── parameters.py      # resolve(guardrails, tier, profile) → ResolvedParameters (pure)
├── authorization.py   # pattern matching, deny wins, run scope, tool scopes (pure)
├── store.py           # SQL: policy_decision, run_parameter_set, evidence queries
└── predicates/
    ├── __init__.py    # registry bound to predicates.yaml (exact match checked at start-up)
    ├── tables.py      # all_rows_*, column_*, no_open_rows, size-like helpers
    ├── records.py     # evidence_exists, is_signed/frozen/live/provisioned/pinned, approved_by, all_statuses_in, waivers, in_directory
    ├── design.py      # every_req_*, tools, token budget, data classes, hitl, permissions_subset, design deviation
    ├── evaluation.py  # thresholds, cost/latency, judge, scenarios, threats, assurance
    ├── operations.py  # rollout, incidents, monitors, telemetry, baselines, windows, hashes
    └── change.py      # reentry_consistent, class_at_least_if, classification_disputed, has_change_class
data/synthetic/
├── evidence.yaml      # synthetic env, ci, sbom, redteam, dlp, telemetry, change, template, dataset, release, portfolio, retirement
└── artifacts/T0.yaml … T9.yaml   # control-passing artifacts for the stub agent
db/migrations/versions/0004_policy.py
tests/
├── unit/policy/           # predicates (one test module per group), parameters, authorization, values, compiler
├── integration/policy/    # evidence provider, decision log, all-rules sweep, engine in orchestrator
└── scenario/              # existing 003 scenarios now run with the real engine
```

**Structure Decision**: this fills the `policy/` layer from build plan §5. Pure parts
(`parameters`, `authorization`, `values`, `predicates`) are separate from I/O (`evidence`,
`store`), as in 003. Synthetic data is kept under `data/` (demo data, not specs), is copied
into the image, and its location is set by `ADLC_SYNTHETIC_DIR`.

## Complexity Tracking

No constitution violations; nothing to justify.
