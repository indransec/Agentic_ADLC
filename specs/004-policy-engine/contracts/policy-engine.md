# Contract: Policy engine

`CelPolicyEngine` implements the feature 003 protocol unchanged:

```text
evaluate(expression: str, context: EvalContext) -> EvalResult       # never raises
authorize(actor: str, action: str, resource: str, context: EvalContext) -> bool
authorize_decision(actor, action, resource, context) -> (bool, reason)   # same decision, with reason
```

`EvalContext`: `terminal_id`, `check_id`, `run_id`, `usecase_id` and `variables` (as in
003). `EvalResult`: `passed`, `value`, `reason`, `synthetic`.

## Evaluate: steps

1. **Compile.** The program is compiled from the expression text and cached. A parse error
   gives not passed: `evaluation error: <message>`.
2. **Check references.** The expression's references are found (002 `expressions`). For each
   reference, the evidence provider is asked for the root, and the full path is followed
   (`T0.risk_classification.tier`; a path into a table reads the first row). A root that is
   `NOT_AVAILABLE`, or a member that is missing, is bound as an error value,
   `evidence not available: <path>`. CEL's own logic then decides whether the rule needed it:
   `run.mode != "retire" || retirement.x` is true in evolve mode without retirement evidence,
   while any rule whose result depends on the missing value fails with that reason.
3. **Activate.** The activation is built: `T<n>`, `run`, `intake`, `trigger`, `timeline`, `tier`,
   `param` and the external sources, as CEL values (contracts/evidence.md).
4. **Evaluate.** Predicates record a failure reason as they run.
5. **Map the result.**

   | Outcome | `passed` | `reason` |
   | --- | --- | --- |
   | Result `true` | true | `passed` |
   | Result `false` | false | The first predicate failure reason, else `rule is false: <expression>` |
   | Not a bool | false | `rule did not return true/false: <value>` |
   | `CELEvalError` or any exception | false | `evaluation error: <message>` |
   | Took longer than 1 s | false | `evaluation too slow (<ms> ms)` |
   | Evidence too large (R-03) | false | `evidence too large: <ref>` |

6. **Apply the fail-safe rule.** For check ids starting `plus:` or `external:`, any outcome
   other than true or false becomes `passed=true`. For check ids starting `then_when:`, it
   becomes `passed=false`. In both cases `fail_safe=true`, and the reason gets the prefix
   `fail-safe: `.
7. **Record.** A `run.policy_decision` row is written, and the call runs in the span
   `adlc.policy.evaluate`, with the check id and run attributes.

## Authorize: steps

contracts/authorization.md. Writes a decision row with `kind=authorize`, in the span
`adlc.policy.authorize`.

## Parameters

`param.<name>` comes from the run's frozen `run.run_parameter_set`, resolved on first use
(research R-06). A guardrail with no value for the tier makes `param.<name>` not available
(`parameter not resolved: <name>`).

## Start-up checks

- The predicate library's names and arities equal `predicates.yaml` exactly. A missing or extra
  predicate stops the process with an error listing them (FR-002).
- Every predicate in the library is generic: none names a terminal, role or event (constitution
  I, scan).
