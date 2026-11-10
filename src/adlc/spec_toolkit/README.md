# adlc.spec_toolkit

Validates and registers ADLC terminal specs and shared catalogues (feature 002;
`specs/002-terminal-spec-toolkit/`).

## Commands

| Command | Does |
| --- | --- |
| `adlc-spec validate [adlc-specs] [--format json] [--baseline-ref REF \| --no-baseline] [--min-severity …]` | Runs L1–L5 and reports every finding with file, line, rule id. Exits 1 on any error. |
| `adlc-spec register [adlc-specs] [--dry-run]` | Validates (no git baseline), then registers new versions into the `ADLC_DB_*` data store in one locked transaction, using the schema-owner identity. |
| `make spec-validate` / `make spec-register` | The same, as used by `make check` and on the host |

## Levels and rules

- **L1** parse and layout (P-01..P-03)
- **L2** JSON Schema (S-01..S-03; schemas in `adlc-specs/schema/`)
- **L3** single-spec rules (`rules/single_spec.py`)
- **L4** cross-spec and catalogue rules, including the event and route graph (`rules/cross_spec.py`, `graph.py`)
- **L5** version-bump rules against git `main` and, at registration, against the registry (`rules/versioning.py`)

Every rule id is documented in `specs/002-terminal-spec-toolkit/contracts/validation-rules.md`.
A test keeps the code and that table in step.

## Adding a rule

1. Write a negative fixture: `tests/fixtures/specs/<rule-id>-<case>/patch.yaml` (patch applied to the
   `_valid` bundle) and `expected.yaml` (expected rule id, file and path).
2. Add a function with `@REGISTRY.rule("V-nn", "L4", "error", "summary")` in the right module.
   It must iterate over specs and catalogues and never name a terminal, role or event
   (constitution I; `tests/unit/test_no_hardcoded_values.py`).
3. Add the rule's row to `contracts/validation-rules.md`.

## Reading registered specs

Use `SpecRegistry` (`registry.py`), never YAML, at run time:

```python
registry = SqlSpecRegistry(app_engine)  # or InMemorySpecRegistry.from_bundle(bundle)
registry.terminals_opened_by("T4.rework.implementation")  # (TerminalRef("T3", "1.0.0"),)
registry.outcome_route("T5", "exception").recheck_at  # ("T6", "T8")
registry.timeline("T2", "medium").max_clarification_rounds  # 2
```

Both implementations use `projections.py`, so they always agree. Unknown keys return `()` or `None`.
