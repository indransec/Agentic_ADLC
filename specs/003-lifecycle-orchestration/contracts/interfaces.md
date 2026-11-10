# Contract: Orchestration interfaces (constitution VII)

```text
class TerminalRun(Protocol):                       # engine.py: PostgresTerminalRun
    apply(run_id, signal, expected_version=None) -> RunSnapshot     # one transaction
    advance(run_id) -> bool                        # one automatic step, outside a transaction
    open(usecase_id, terminal_id, trigger) -> RunSnapshot

class Router(Protocol):                            # router.py
    handle(event: Event, conn) -> None             # runs inside the delivery transaction

class PolicyEngine(Protocol):                      # feature 004 replaces StubPolicy
    evaluate(expression: str, context: EvalContext) -> EvalResult   # value, passed, reason
    authorize(actor: str, action: str, resource: str, context) -> Decision

class AgentRunner(Protocol):                       # feature 006 replaces StubAgent
    build(context: BuildContext) -> AgentResult    # Artifacts | Clarification | BudgetExceeded

class Reviewer(Protocol):                          # feature 006 replaces StubReviewer
    review(context: ReviewContext) -> ReviewResult # Recommendation | Clarification

class Clock(Protocol):                             # tests use a controllable clock
    now() -> datetime
```

## `BuildContext`

What the agent receives (SA §7.2). The full context builder arrives in 006.

| Field | Content |
| --- | --- |
| `run_id`, `terminal_id`, `spec` | Pinned spec JSON (from `SpecRegistry.entry`) |
| `usecase` | id, name, intake text, risk tier |
| `trigger` | Event type plus context: rework comment, root cause, causing run id, causing ledger key, operational event payload |
| `previous_artifacts` | Artifacts of the latest closed run of this terminal, if any |
| `clarifications` | Rounds so far, with answers |
| `attempt` | Automated retry number, and the failed control results when retrying |

`ReviewContext` holds the spec checklist, the artifacts and the control results, never the
builder's reasoning (SA §7.2 point 5).

## Tracing (constitution X)

Every call to `evaluate`, `authorize`, `build` and `review`, and every routing step, runs
inside an OpenTelemetry span named `adlc.<component>.<operation>`, with attributes `run_id`,
`usecase_id` and `terminal_id`.
