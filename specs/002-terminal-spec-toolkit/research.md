# Research: Terminal Spec Toolkit (002)

Every decision lists the choice, the reason, and the alternatives rejected. Nothing in the
Technical Context is left open.

## R-01 Expression language: CEL, parsed by cel-python

- **Decision**: conditions and rules are CEL expressions (SA §5.5, §17 "YAML + JSON Schema +
  CEL"). This feature only parses them with `celpy.celparser.CELParser` and extracts the
  identifiers. Feature 004 evaluates them. TDS Annex B.3 operators map to CEL: `and` → `&&`,
  `or` → `||`, `not` → `!`, `in [a, b]` → `in ["a", "b"]`. Existence words (`exists`,
  `signed`, `frozen`, `provisioned`, `pinned`) become named predicates whose names do not clash
  with CEL macros: `evidence_exists(T1.eval_thresholds)`,
  `is_signed(T5.assurance_attestation)`, `is_frozen(…)`, `is_provisioned(…)` and
  `is_pinned(…)`.
- **Evidence**: a spike parsed every expression shape the conversion needs, including member
  access on terminal ids (`T0.status`), list membership, predicate calls with list arguments,
  `param.<name>` and boolean chains. It rejected malformed input with `CELParseError`.
- **Rationale**: a standard grammar with an evaluator available for 004 (same library), and no
  home-grown parser to maintain.
- **Alternatives**: keep the TDS B.3 English-like grammar with our own parser (more code, and
  004 would need its own evaluator); full evaluation now (out of scope, belongs to 004).

## R-02 Names inside expressions

Each identifier root in an expression must resolve to one of these:

| Root | Resolves against |
| --- | --- |
| `T<n>` | terminal id: artifact or emitted value of that terminal (V-02 rules apply) |
| `param` | guardrail parameter (`param.<name>`; replaces TDS `tier.<param>` for guardrailed values) |
| `tier` | the spec's own `controls.tiering` key (process-depth settings) |
| `profile` | use-case profile fields (artifacts selected, thresholds) for metric-iterating controls |
| `timeline` | the spec's own `timeline` block (`timeline.max_rework_cycles`, `timeline.escalate_after`), so escalation rules read the configured limit instead of a literal |
| `run` | run variables: `run.rework_count`, `run.age`, `run.now`, `run.risk_tier`, `run.usecase_id`, `run.run_version`, `run.mode` (TDS B.3; namespaced so they cannot collide) |
| evidence source | a prefix from `evidence_sources.yaml` (`intake`, `env`, `change`, `template`, `dataset`, `trigger`, `release`, `telemetry`) |
| function | a predicate from `predicates.yaml`, or a CEL built-in from an allow-list (`size`, `has`, `int`, `double`, `string`, `duration`, `timestamp`, `all`, `exists`, `exists_one`, `map`, `filter`) |

- **Rationale**: one namespace per kind makes rule V-12 simple and keeps 004's evaluation
  context well-defined.
- **Alternatives**: bare run variables as in the TDS (`rework_count`). They are ambiguous
  with artifact columns, so they are namespaced under `run.`, and the change note records it.

## R-03 Schema technology and editor support

- **Decision**: JSON Schema draft 2020-12, validated with `jsonschema`
  (`Draft202012Validator`), with `additionalProperties: false` on every object and `$defs`
  for the B.1 types (`semver`, `duration`, `tiered`, `event`, `permission`, `scope`,
  `evidence_ref`). Each terminal YAML starts with
  `# yaml-language-server: $schema=../schema/terminal.schema.json`, which VS Code (Red Hat
  YAML) and JetBrains understand.
- **Rationale**: Annex B is already a dictionary of typed fields, and JSON Schema expresses it
  directly. Editors validate it without plugins of our own.

## R-04 L1 locations

- **Decision**: load with ruamel.yaml round-trip mode. A path→(line, col) index comes from
  `CommentedMap.lc`. jsonschema errors carry `absolute_path`, so locations map back to
  lines. A parse error gives `problem_mark` (line and column).
- **Alternative**: the safe loader (loses positions).

## R-05 Rule engine

- **Decision**: each rule is a function `(bundle: SpecBundle) -> Iterable[Finding]`,
  registered with a decorator carrying `id`, `level`, `severity` and `summary`. Rules run in
  level order; L3 and above skip files that failed L1 or L2 and report them as `skipped`.
  `contracts/validation-rules.md` is generated-checked: a unit test asserts that the rule
  table and the document list the same ids.
- **Rationale**: FR-009 (stable, documented ids). A new rule is one function, one fixture and
  one doc row.

## R-06 L4 graph (networkx)

- **Decision**: a directed graph with nodes for terminals and events.
  - Edges: `event → terminal` for each `trigger.on`; `terminal → event` for each outcome
    the terminal can emit (`T<n>.<status>`, `T<n>.rework.<cause>` per its `route_by_root_cause`
    keys, `T8.event.<name>` per monitors, `T9.reentry.T<k>` per change classes, `T7.rollback`).
  - Special destinations (`human_completion`, `owning_terminal`, boards) are sink nodes from
    `route_destinations.yaml`.
  - V-02 checks `nx.has_path(referenced_terminal, referencing_terminal)`.
  - V-03 checks that every trigger event has a producer or is external in `events.yaml`.
  - V-22 checks that every terminal can reach a terminating outcome (`terminate` or
    `lifecycle_closed`).
- **Rationale**: spec clarification Q5 (reachability, no numeric order); networkx is small,
  pure Python and BSD-licensed.

## R-07 Separation of duties from data

- **Decision**: `permissions.yaml` lists the permission verbs (Annex A.4) and also
  `duty_groups`. Each group is a list of permission patterns, for example
  `build: [write:repo.*, open:pull_request, run:ci_pipeline]`,
  `evaluate: [write:eval_store, write:T4.artifacts]` and
  `deploy: [run:cd_pipeline.*, set:traffic_split]`. Rule V-16 fails when one terminal's
  `allow` list matches patterns from more than one duty group.
- **Rationale**: SA §9 ("builder, evaluator and deployer have disjoint write permissions;
  enforced at spec release") without naming terminals in code (constitution I).

## R-08 Guardrails and parameters

- **Decision**: `guardrails.yaml` has one entry per parameter with these fields:
  - `name` (Annex A.4 `<measure>_<min|max>`)
  - `unit` and `direction` (`max` or `min`)
  - `tighten_only` (bool)
  - `values: {low, medium, high}`
  - `proposed_default` (bool, FR-017)
  - `source` (the TDS location)

  Specs reference them as `param.<name>`. Rule V-19 checks tighten-only monotonicity: for
  `max` limits, high ≤ medium ≤ low; for `min` limits, high ≥ medium ≥ low.
- **Moved to guardrails** (clarification Q2):
  - `injection_success_max`, `jailbreak_success_max` (T5 tiering)
  - `judge_agreement_min` (T4 CTL-T4-05)
  - `unit_coverage_min_pct` (T3 CTL-T3-02)
  - `test_scenarios_min_count` (T1 tiering)
  - `eval_cases_min_count`, `human_label_cases_min_count` (T4 tiering)
  - `rai_metric_classes_required` (T1 tiering; a list-valued guardrail whose
    tighten-only rule is "superset as risk increases")
- **Kept in `controls.tiering`**: red-team mode, threat model depth, architecture board
  review, adversarial depth, PIA depth, rollout stages, CAB required, canary percentage, soak,
  hypercare.

## R-09 Normalisation and hashing

- **Decision**: the normalised form is the YAML loaded to plain Python and serialised as JSON
  with `sort_keys=True`, `separators=(",", ":")` and `ensure_ascii=False`. Comments and key
  order are dropped. The content hash is `sha256:<hex>` of that UTF-8 string (Annex A.5).
  Catalogues, checklists and playbooks are hashed the same way (playbooks hash their full
  file bytes, because their body is content).
- **Rationale**: FR-023; formatting-only edits do not change the hash.

## R-10 L5 version rules

- **Decision**: baselines follow clarification Q1. At validate time the baseline is
  `git show <ref>:<path>`, where `<ref>` comes from `--baseline-ref` (default from
  `ADLC_SPEC_BASELINE_REF`, else `origin/main`). If the ref is missing (shallow clone,
  container without git), L5 against git is skipped with a warning finding. At register time
  the baseline is the latest registered version of the same terminal or catalogue.

| Change between baseline and current (normalised) | Minimum bump |
| --- | --- |
| No change | none; a bump is allowed but reported as info |
| Only `description` / `notes` / checklist item text | patch |
| Additions only (new trigger event, artifact, column, control, playbook, catalogue entry) | minor |
| Removal or change of a trigger event, route destination, root cause, artifact, column, permission, status right, guardrail value, or applicability | major |
| Version lower than baseline | always an error |

- **Rationale**: changes that can break pinned use cases need a major bump. This is the rule
  table FR-008 points to.

## R-11 Registry immutability and status transitions

- **Decision**: these tables get `BEFORE DELETE OR TRUNCATE` triggers that raise for every
  identity (as `ledger.reject_mutation` in 001): `spec_registry`, `spec_catalogue`,
  `playbook_registry` and every projection table.
  - Projection tables and `playbook_registry` also refuse every `UPDATE`.
  - `spec_registry` and `spec_catalogue` have a `BEFORE UPDATE` trigger that allows only a
    change of `status` (plus its `*_at` timestamp) along `active → deprecated → retired`, or
    `active → retired`.
  - A move to `retired` is refused while `usecase_spec_pin` references the version.
  - A partial unique index `(terminal_id) WHERE status = 'active'` enforces one active
    version per terminal. Catalogues have the same index on `catalogue_name`.
- **Rationale**: FR-021 and FR-022 are enforced by the database, not by code.

## R-12 Registration transaction and concurrency

- **Decision**: registration runs as follows:
  1. Validate fully (no git baseline in containers). Any error aborts before connecting.
  2. Open one owner-identity transaction and take
     `pg_advisory_xact_lock(hashtext('adlc.spec.register'))`.
  3. For each catalogue, then each terminal: compare its hash with the latest registered row.
     - Equal: skip.
     - Changed with the same version: abort the whole transaction, naming the item.
     - New version: L5 rules against the registered normalised JSON; then deprecate the old
       active row, insert the new row and insert its projections.
  4. Insert playbooks by `(id, version)` when the pair is new. The same pair with a different
     hash aborts.
  5. Commit and log one summary line.
- **Rationale**: FR-019 to FR-022 and the concurrency edge case (the second registrant waits
  for the lock, then sees "no changes").

## R-13 Where registration runs (clarification Q4)

- **Decision**:
  - `make spec-register` runs `uv run adlc-spec register` on the host with `.env` (owner
    identity).
  - Compose gets a one-shot `register` service (API image,
    `command: adlc-spec register`), which depends on `migrate` completing; `api` depends on
    `register`.
  - CI: `make check` runs `spec-validate` (L1–L5 with `origin/main`; `actions/checkout`
    uses `fetch-depth: 0`). The integration test suite registers the real `adlc-specs/` into a
    testcontainers database (the throwaway registry).
- **Rationale**: FR-023a and FR-023b; no runner needed on the demo host.

## R-14 Read interface

- **Decision**: a `SpecRegistry` Protocol with the methods below. All results are frozen
  dataclasses; unknown keys return `()` or `None`.

  ```text
  terminals_opened_by(event) -> tuple[TerminalRef]
  outcome_route(terminal, status, root_cause=None, version=None) -> RouteTarget | None
  event_route(terminal, event, version=None) -> EventRouteTarget | None
  change_class_route(terminal, change_class, version=None) -> ChangeClassRoute | None
  timeline(terminal, risk_tier, version=None) -> TimelinePolicy | None
  entry(terminal, version=None) -> RegistryEntry | None
  catalogue(name) -> CatalogueEntry | None
  ```

  `SqlSpecRegistry(engine)` implements it with plain SQL through SQLAlchemy Core and is used
  with the app identity (SELECT only).
- **Rationale**: FR-024 and FR-025. 003 depends on the Protocol, so tests can use an
  in-memory fake.

## R-15 Conversion approach

- **Decision**: the YAMLs are authored by hand, one terminal per task, each validated as it
  lands. `CONVERSION.md` has one table per terminal: TDS element, TDS location, result
  (`kept`, `converted`, `renamed`, `moved`, `removed`), new location and reason. The TDS
  wording of every converted condition or rule is kept as the item's `description` (FR-013).
  Checklist item text is split from the ids (`CHK-T0-01 problem is measurable` → id
  `CHK-T0-01`, text "Problem is measurable") into `checklists/t<n>.yaml`. Playbook stubs carry
  front matter (`id`, `version`, `title`, `owner_role`, `status: stub`) and a body saying
  which feature fills them.
- **Rationale**: conversion is judgement work. A script would hide decisions that the record
  must make visible (SC-003).

## R-16 Dictionary additions (recorded in `schema/DICTIONARY-CHANGES.md`)

| Change | Reason |
| --- | --- |
| `evidence.artifacts[].applicability: {mode: mandatory\|conditional\|optional, when?: expr, reason?: string}` replaces `required` | SA §5.2; TDS `required: on_retire` becomes `{mode: conditional, when: "run.mode == \"retire\""}` |
| `prerequisites[].description`, `controls.automated[].description` | keep TDS wording (FR-013) |
| `controls.checklist.items` is a list of ids; text lives in `checklists/t<n>.yaml` | separates data from text; V-10 checks the ids exist |
| `timeline.clarification_sla` (duration), `timeline.max_clarification_rounds` (int ≥ 0), `timeline.max_auto_retries` (int ≥ 0, optional, default 3, proposed default) | SA §6.2, TDS Annex A.3 note |
| `timeline.reminder_after` / `escalate_after` for `mode: continuous` measured from `review_due` | TDS T8 `2d_past_review_due` |
| `authorities.sign_off.plus: [{role, when: expr}]` | TDS T3 free text |
| `outcome_model.<status>.notify: [role]` on escalate; `route` may be a destination from `route_destinations.yaml` | T5–T9 escalation to boards and role groups |
| `outcome_model.pass.alternatives: [destination]` | T9 `or: lifecycle.closed` |
| `outcome_model.<status>.description` | T6 `example`, T9 `meaning` |
| run variables namespaced as `run.*`; guardrail values as `param.*` | R-02 |
| Annex A naming applied to metrics, columns and guardrails | SA Annex A closing note |
| `metadata.schema_version: "1.1.0"` | dictionary version after these additions |
