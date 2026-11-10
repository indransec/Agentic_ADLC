# adlc.policy

The deterministic policy engine (feature 004; SA §9 and §5.4; constitution VI and XI). Every
rule that can be computed is decided here, outside the models.

## What it does

| Call | Used for |
| --- | --- |
| `evaluate(expression, context)` | Prerequisites at run open; automated controls after every build; approver and external-body conditions; event follow-on conditions |
| `authorize(actor, action, resource, context)` | Agent and tool actions (features 006 and 010): run scope, then deny, then allow, then default deny |

Both implement the feature 003 `PolicyEngine` protocol. Each call writes one append-only row in
`run.policy_decision`, with its inputs and reason, and runs in the span
`adlc.policy.<evaluate|authorize>`.

## How `evaluate` works

1. The expression (CEL, as validated by 002) is compiled once and cached (`compiler.py`).
2. Each referenced path is followed in the evidence (`activation.py`):
   - a path into a table reads its first row;
   - missing evidence becomes an error value, so CEL's own logic decides whether the rule
     needed it (`run.mode != "retire" || retirement.x` holds in evolve mode).
3. The 60 catalogued predicates run (`predicates/`), each explaining a failure: table, row and
   column, or the missing path.
4. Anything but `true` is **not passed**, with a reason. The engine never raises: errors, missing
   evidence, non-bool results, more than 1 s, more than 10,000 rows or more than 100,000
   characters all fail closed.
5. Approval conditions (`plus:`, `external:`) that cannot be evaluated require the approval.
   Follow-on conditions (`then_when:`) that cannot be evaluated do not fire.

## Evidence (`evidence.py`)

| Source | From |
| --- | --- |
| `T<n>` | The latest closed run of that terminal (or the run itself): status, signers, waivers, `bound_to`, artifacts, emitted values |
| `run`, `intake`, `trigger`, `timeline`, `tier`, `waivers` | Feature 003 records and the pinned spec |
| `param` | `parameters.py`: resolved within guardrails when the run opens, frozen in `run.run_parameter_set` |
| `directory` | `directory.py`: the account file |
| `env`, `ci`, `sbom`, `redteam`, `dlp`, `telemetry`, `change`, `template`, `dataset`, `release`, `portfolio`, `retirement`, `profile` | Later features. Meanwhile `data/synthetic/` supplies them, and every decision that reads them is labelled `synthetic` |

## Plugging in later features

- **005**: implement `ProfileSource`, so use-case values reach parameter resolution.
- **006 and 010**: call `authorize` before every agent action and tool call, with the actor
  `agent:<run_id>`.
- **009–012**: register a real `EvidenceProvider` for their source. It is layered before the
  synthetic one, which stops being used for that source.
