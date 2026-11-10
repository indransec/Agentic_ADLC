# Research: Policy Engine (004)

## R-01 Evaluator: cel-python programs with a function library

- **Decision**: compile each expression once with `celpy.Environment().compile(text)` and cache
  the compiled program by expression text. Evaluate with an activation dict of CEL values. The
  60 catalogued predicates are passed as the program's custom functions; built-ins such as
  `size`, `in`, `&&` and `||` stay standard CEL.
- **Rationale**:
  - cel-python is already the 002 parser, so expressions validated at registration are exactly
    the ones evaluated.
  - It is non-Turing-complete, side-effect free and Apache-2.0.
  - A spike (2026-11-10) evaluated `all_rows_have(...) && size(...) >= n && T0.status in [...]`
    with custom functions.
  - A missing member raises `CELEvalError`, which we turn into "not passed".
- **Alternatives**: a hand-written evaluator (more code, two languages to keep in step); OPA
  with Rego (a second language for spec authors, and an extra service).

## R-02 Fail closed and reasons

- **Decision**: `evaluate` never raises.
  1. Before evaluating, it lists the expression's references (002 `expressions.references`) and
     asks the evidence provider for each root. If any root that is needed is not available, the
     result is "not passed" with `evidence not available: <source>`, and the expression is not
     evaluated.
  2. During evaluation, predicates explain a failure in a reason collector bound to the call,
     for example `T1.kpis row 3: baseline is not numeric ('n/a')`.
  3. The first failing predicate's reason becomes the result reason. If no predicate failed but
     the expression is false, the reason is `rule is false: <expression>`.
  4. `CELEvalError`, `TypeError` and any other exception give `evaluation error: <message>`.
  5. A result that is not a bool, for a check that must be bool, gives
     `rule did not return true/false`.
- **Rationale**: auditors and approvers need a precise reason (FR-003), and no failure mode may
  let a gate through (FR-004).

## R-03 Limits

- **Decision**:
  - **Size**: tables larger than 10,000 rows, or text values longer than 100,000 characters,
    are not loaded. The check fails with `evidence too large`.
  - **Time**: CEL has no loops beyond bounded macros, so evaluation time is bounded by input
    size. The engine measures each evaluation, and a result that took longer than 1 s is
    recorded as not passed (`evaluation too slow`).
- **Rationale**: the edge case "a rule takes too long or grows too large" is covered without
  threads or signals.

## R-04 Evidence model (contracts/evidence.md)

- **Decision**: `EvidenceProvider.get(source, ctx) -> Evidence | NOT_AVAILABLE`.
  - **Built-in real sources**:
    - `T<n>` (terminal evidence);
    - `run`, `intake`, `trigger`;
    - `timeline` (pinned spec, use case tier);
    - `tier` (the terminal's `controls.tiering[<tier>]`);
    - `param` (frozen parameter set);
    - `waivers` (for waiver predicates);
    - `directory`.
  - **Terminal evidence `T<n>`**, for the latest closed run of `T<n>` (or the run being
    checked, when `T<n>` is its own terminal):
    - record fields: `status`, `signed_by` (sign-off people), `closed_at`, `run_version`,
      `waivers`, `bound_to` (the spec's `ledger.bound_to` reference, resolved);
    - emitted values: `T<n>.<name>`, from the ledger record's `emitted` (for example
      `T4.eval_baseline`);
    - artifacts: `T<n>.<artifact>` as a list of rows, `T<n>.<artifact>.<column>` as the first
      row's value.
  - **Later sources** (`env`, `ci`, `sbom`, `redteam`, `dlp`, `telemetry`, `change`,
    `template`, `dataset`, `release`, `portfolio`, `retirement`, `profile`) answer
    `NOT_AVAILABLE` unless a registered provider supplies them.
  - **`CompositeEvidenceProvider`** asks the real provider first and the synthetic provider
    second, and marks a value `synthetic` when it came from the synthetic one.
- **Rationale**: one interface for 009–012 to plug into (user choice); synthetic use is visible
  (clarification).

## R-05 Synthetic data (clarification 2026-11-10)

- **Decision**: synthetic data is enabled in dev and demo; the setting `ADLC_SYNTHETIC_DIR`
  (default `data/synthetic`) points at the data, and the value `off` disables it.
  - **`data/synthetic/evidence.yaml`** holds values per source, with consistent hashes across
    sources (for example `env.test.deployed_hash` = the synthetic T3 package hash =
    `release.package_sha256`).
  - **`data/synthetic/artifacts/T<n>.yaml`** holds control-passing artifacts. The stub agent
    uses them when a file exists for the terminal, falling back to placeholders otherwise. A
    test can still script overrides.
  - **Labelling**: every decision that read a synthetic value records `synthetic: true`, and the
    003 `EvalResult.synthetic` carries it into `control_results`.
- **Rationale**: the demo runs with real checks, and audit honesty is kept.

## R-06 Parameter resolution (SA §5.4)

- **Decision**: `resolve(guardrails, tier, profile_values) -> ResolvedParameters`, a pure
  function. For each guardrail, the value is the profile value when present and valid, otherwise
  the tier value.
  - **Valid** means:
    - the value is numeric;
    - for a `tighten_only` guardrail, a `max` value must be ≤ the tier value and a `min` value
      ≥ the tier value.
  - A value that is not valid is rejected, with the reason.
  - The same direction rule applies to guardrails without `tighten_only` (FR-013). For a
    tighten-only guardrail, only an exception can loosen it.
- **Frozen**: the set is resolved when the run opens (the orchestrator's first policy call for
  the run, its prerequisites) and inserted into `run.run_parameter_set` (append-only, one row
  per run, `ON CONFLICT DO NOTHING`). Later evaluations read it back. Each run, including a
  rework run, has its own set.
- **Tier**: a use case with no tier uses `medium` (as in 003).
- **Profile**: until feature 005, `ProfileSource` returns no values, so the guardrail values
  apply.

## R-07 Authorization (contracts/authorization.md)

- **Decision**: `authorize(actor, action, resource, ctx)`.
  - **Request**: the request string is `<action>:<resource>` (for example `write:T1.artifacts`),
    matched with `fnmatch` against the run's terminal spec `authorities.allow` and
    `authorities.deny`.
  - **Tools**: `mcp:<server>:<op>` requests are matched against `authorities.tool_scopes`.
  - **Order**: deny wins, then allow, then default deny.
  - **Run scope**: the actor id `agent:<run_id>` (or `reviewer:<run_id>`) must equal
    `ctx.run_id`. An actor bound to another run, or with no run, is refused as out of scope.
  - **Result**: the protocol returns bool. The reason goes to the decision record, and
    `authorize_decision()` returns `(allowed, reason)` for callers that need it.
- **003 change**: the engine's agent and reviewer actor ids become `agent:<run_id>` and
  `reviewer:<run_id>` (they were `agent:<terminal>`), so run scope can be checked.

## R-08 Decision log

- **Decision**: one `run.policy_decision` row per call, written in its own short transaction.
  - **Why separate**: decisions are facts even if the caller's transaction later rolls back.
    Because it doesn't share the caller's transaction, it doesn't take the caller's row locks
    and can't deadlock with it.
  - **Inputs**: scalar values are stored in full. Tables are stored as a reference
    (`T1.kpis@UC-0001/T1/run-1`, row count, content hash), not copied.
  - **Order**: the rows are indexed by `(run_id, decided_at, policy_decision_id)` for ordered
    reads.
- **Rationale**: FR-019 to FR-021, with a bounded record size.

## R-09 Conditions with a fail-safe direction (FR-018)

- **Decision**: the check id prefix decides what happens when a condition can't be evaluated:
  - `plus:` and `external:` are approval conditions: the answer is `passed=True` (the
    approval is required);
  - `then_when:` is an event follow-on: the answer is `passed=False` (no follow-on);
  - prerequisites and controls fail closed (`passed=False`).

  The reason always says that the value was decided by the fail-safe rule.
- **Rationale**: an unclear condition never reduces human approval and never fires an
  automated rollback.

## R-10 Directory (`in_directory`)

- **Decision**: a `Directory` protocol. The account-file directory reads
  `ADLC_ACCOUNTS_FILE` when set (the orchestrator container mounts it read-only, as the API
  does). Without it, the directory is not available and the check fails closed, unless the
  synthetic provider supplies `directory`.
