# Implementation Plan: Terminal Spec Toolkit

**Branch**: `002-terminal-spec-toolkit` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-terminal-spec-toolkit/spec.md`

## Summary

This feature delivers the following:

- **`adlc-spec` CLI** in `src/adlc/spec_toolkit/`. `validate` checks `adlc-specs/` at levels
  L1–L5 through a data-driven rule table. `register` writes the specs and catalogues into the
  `spec` schema in one locked transaction.
- **Specs and catalogues**: JSON Schemas for terminal specs and for every catalogue, the
  converted T0–T9 YAMLs, the shared catalogues, checklist files, playbook stubs, a conversion
  record and a dictionary change note.
- **Migration `0002`**: registry, projection, catalogue, playbook and pin tables, all
  immutable apart from the registry status transitions.
- **Read interface**: a `SpecRegistry` Protocol with a SQLAlchemy implementation for 003 and
  later features.
- **Integration with feature 001**: `make spec-validate` runs inside `make check`, and
  `make up` registers specs after migrating.

Decisions are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (existing `adlc` package, uv)

**Primary Dependencies**:

- Already used: ruamel.yaml, Typer, SQLAlchemy, Alembic
- New: jsonschema, networkx, cel-python (parser only)

Licences are listed below.

**Storage**: PostgreSQL schema `spec` (migration `0002`)

**Testing**: pytest with negative fixtures per rule; testcontainers PostgreSQL for the
registry; a snapshot test of the demo routing answers

**Target Platform**: developer machines, CI (`ubuntu-latest`), and the `migrate`/`register`
one-shot containers in Compose

**Project Type**: CLI and library inside the platform package, plus data files in
`adlc-specs/`

**Performance Goals**: validate the full folder in < 10 s (SC-001); register all specs on an
empty store in < 30 s (SC-005)

**Constraints**:

- No terminal-specific code (constitution I).
- The registry is immutable apart from status transitions (FR-021).
- Registration is one transaction and serialised (FR-019, FR-022).
- L5 reads `main` through git; containers have no git and skip L5 against git, using the
  registry baseline instead (FR-011).

**Scale/Scope**:

- 10 terminal specs and about 14 catalogues.
- About 31 playbook stubs and 10 checklist files.
- About 25 validation rules.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| jsonschema | L2 schema validation (draft 2020-12) | MIT |
| ↳ attrs, referencing, jsonschema-specifications, rpds-py | jsonschema runtime | MIT |
| networkx | L4 event and route graph (reachability, coverage) | BSD-3-Clause |
| cel-python (`celpy`) | Parse CEL expressions; evaluation is feature 004 | Apache-2.0 (licence file in dist) |
| ↳ lark | CEL grammar parser | MIT |
| ↳ pendulum, python-dateutil, tzdata | celpy runtime types | MIT; BSD-3-Clause / Apache-2.0; Apache-2.0 |
| ↳ google-re2 | celpy regex support | BSD-3-Clause |
| ↳ pyyaml, jmespath, tomli | celpy runtime | MIT |
| types-networkx, types-jsonschema (dev) | Type stubs for mypy strict | Apache-2.0 |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | The toolkit iterates over whatever the specs and catalogues declare. Rules are data-driven: duty groups, destinations and evidence sources come from catalogues. The no-hard-coded-values scan is extended to `spec_toolkit`. | Pass |
| II Superset, not values | Numeric safety limits move to `guardrails.yaml`, and specs reference `param.<name>` (FR-014). Applicability is on every artifact. | Pass |
| III Agents build, humans decide | Rule V-15 enforces status rights for every spec | Pass |
| IV Separation of duties | Rule V-16 checks duty groups declared in `permissions.yaml` | Pass |
| V Evidence-first | Registry and projections are append-only by trigger; spec hash recorded per version | Pass |
| VI Deterministic first | Every free-text rule becomes CEL or a named predicate (FR-013) | Pass |
| VII Interfaces | `SpecRegistry` Protocol; storage behind it (FR-025) | Pass |
| VIII Open source | New dependencies listed with OSI licences above | Pass |
| IX Test first | Routing data snapshot, registry immutability and each rule's negative fixture are written before implementation | Pass |
| X Observable | Registration logs one summary line per run; no run steps exist yet | Pass (n/a) |
| XI Secure | Registration uses the owner identity only; the app role has SELECT only on `spec` | Pass |
| XII Simplicity | Projections limited to trigger, outcome route, event route, timeline and change class; everything else stays in the normalised JSON | Pass |
| XIII Naming | Rule V-18 enforces Annex A on specs and catalogues; tables follow A.6 | Pass |

**Post-design re-check**: Pass. One trade-off is recorded: the change-class projection was
added beyond the spec's "at minimum" list because D-7 needs T9 re-entry routing. It stays
within XII because it serves a demo moment.

## Project Structure

### Documentation (this feature)

```text
specs/002-terminal-spec-toolkit/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── adlc-spec-cli.md            # validate / register commands, exit codes, JSON output
│   ├── validation-rules.md         # every rule: id, level, severity, check, example
│   ├── spec-registry-interface.md  # SpecRegistry Protocol and return types
│   └── spec-files.md               # terminal YAML additions, catalogue and checklist formats
├── checklists/
└── tasks.md
```

### Source code and data (repository root)

```text
src/adlc/spec_toolkit/
├── __init__.py
├── cli.py              # Typer app `adlc-spec`
├── loader.py           # L1: ruamel round-trip load, line/col index, SpecBundle
├── schema.py           # L2: jsonschema validation, error → finding mapping
├── expressions.py      # CEL parse + identifier extraction (celpy parser only)
├── catalogues.py       # typed views over shared catalogues
├── graph.py            # L4 event/route DiGraph (networkx)
├── rules/              # rule table + one module per family
│   ├── __init__.py     #   Rule(id, level, severity, doc), registry, run_rules()
│   ├── single_spec.py  #   L3 rules
│   ├── cross_spec.py   #   L4 rules
│   └── versioning.py   #   L5 rules (git baseline; registry baseline in register)
├── findings.py         # Finding model, text + JSON reporters
├── normalise.py        # canonical JSON + sha256 content hash
├── projections.py      # spec → projection rows (pure)
├── register.py         # transactional registration (owner identity, advisory lock)
├── registry.py         # SpecRegistry Protocol + SqlSpecRegistry
└── README.md
db/migrations/versions/0002_spec_registry.py
adlc-specs/
├── terminals/T0.yaml … T9.yaml
├── shared/{roles,risk_tiers,events,root_causes,change_classes,data_classes,model_tiers,
│           mcp_servers,permissions,evidence_sources,route_destinations,predicates,
│           metrics,guardrails}.yaml
├── checklists/t0.yaml … t9.yaml
├── playbooks/*.md (stubs with front matter)
├── schema/terminal.schema.json, schema/catalogues/*.schema.json, schema/checklist.schema.json,
│   schema/DICTIONARY-CHANGES.md
└── CONVERSION.md
deploy/compose.yaml     # + `register` one-shot service between migrate and api
Makefile                # + spec-validate (in check), spec-register
.github/workflows/ci.yml # checkout fetch-depth: 0
tests/
├── fixtures/specs/<rule-id>/…   # one minimal failing bundle per rule
├── unit/spec_toolkit/…          # loader, schema, expressions, rules, normalise, projections
└── integration/spec_toolkit/…   # migration 0002, register, immutability, registry reads,
                                 #   demo routing snapshot
```

**Structure Decision**: the toolkit is one module of the existing package, matching build plan
§5 (`src/adlc/spec_toolkit/`). Specs and catalogues are data in `adlc-specs/`. Validation
rules are small pure functions registered in a table, so a new rule is one function, one
fixture and one documentation row.

## Complexity Tracking

No constitution violations; nothing to justify.
