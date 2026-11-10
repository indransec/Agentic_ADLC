# Contract: Additions to the Feature 003 State Machine

These rows are added to `specs/003-lifecycle-orchestration/contracts/state-machine.md` and to
`adlc.orchestration.states`. There are no new states or signals; these are new `result` values on
existing signals.

| State | Signal | Payload `result` | Next state | Effects |
| --- | --- | --- | --- | --- |
| building | `agent_result` | `failed` | building | `IncrementAutoRetry`, while `auto_retries` is below the limit |
| building | `agent_result` | `failed` | escalated | `Escalate(retry_limit)`, at the limit |
| building | `agent_result` | `model_unavailable` | escalated | `Escalate(model_unavailable)` |
| reviewing | `review_result` | `failed` | escalated | `Escalate(reviewer_failed)` |
| reviewing | `review_result` | `model_unavailable` | escalated | `Escalate(model_unavailable)` |

Payloads also carry `reason` (at most 2,000 characters), which is recorded on the transition.

## Engine behaviour (no transition)

- **While an outage lasts:** a `ModelUnavailable` result received before the outage limit is not
  a signal. The engine records a `deferred` activity (step `build` or `review`) and leases the
  run until now plus the back-off: 30 s doubling, at most 5 min.
- **Outage start:** `run.terminal_run.model_unavailable_since` holds the start of the outage. Any
  other step result clears it.

## Properties (hypothesis, added to `test_state_properties.py`)

1. `failed` and `model_unavailable` results never close a run, and never move it to
   `awaiting_sign_off`.
2. The number of `agent_result failed` transitions back to `building` never exceeds
   `max_auto_retries`. Together with failed blocking controls, the total is at most
   `max_auto_retries` before escalation.
3. `model_unavailable` never changes `auto_retries` or `rework_count`.
