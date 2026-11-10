# Contract: Terminal-run state machine

Pure function `transition(state, signal, ctx) -> Outcome(next_state, effects)` in
`orchestration/states.py`. Anything not listed below is rejected (`InvalidTransition`), and
the run is unchanged. `ctx` carries the pinned spec's limits (`max_rework_cycles`,
`max_clarification_rounds`, `max_auto_retries`), the run counters, the pending waiver and the
sign-offs so far.

## States

- **Automatic** (the advancer works on these): `opened`, `building`, `checking`, `reviewing`.
- **Waiting** (on a signal or timer): `blocked`, `awaiting_clarification`, `awaiting_sign_off`,
  `escalated`.
- **Final**: `closed`.

## Signals and allowed actors

| Signal | Actor type | Payload |
| --- | --- | --- |
| `prerequisites_result` | orchestrator | `met`, `blocked_ids`, `warned_ids` |
| `event_received` | orchestrator | event type, id, payload |
| `agent_result` | agent | `artifacts` \| `clarification` \| `budget_exceeded` |
| `controls_result` | orchestrator | `passed`, `failed_blocking_ids`, results |
| `review_result` | reviewer | `recommendation` \| `clarification` |
| `clarification_answered` | human | clarification id, answers |
| `decide` | human | `pass` \| `rework` \| `exception` \| `terminate`, fields, approver |
| `waiver_decision` | human | `approve` \| `reject` |
| `escalation_completed` | human | artifacts |
| `timer` | orchestrator | `escalate_after` \| `clarification_sla` |
| `open_escalated` | orchestrator | trigger (rework limit at open) |
| `step_interrupted` | orchestrator | — (an automatic step's lease expired: crash or restart) |
| `lifecycle_ended` | human (the person who terminated) | reason (another run of the use case was terminated, or the lifecycle closed) |

## Transition table

| From | Signal / condition | To | Effects |
| --- | --- | --- | --- |
| opened | `open_escalated` | escalated | `escalation_trigger=rework_limit` |
| opened | `prerequisites_result` met | building | — |
| opened | `prerequisites_result` blocked | blocked | — |

The `escalate_after` timer starts when the run is opened (`engine.open_in`), so it is measured from the open.
| blocked | `event_received` | opened | (re-check prerequisites) |
| blocked | `timer` escalate_after | escalated | trigger `timer` |
| blocked | `decide` terminate | closed | CloseRun(terminate) |
| building | `agent_result` artifacts | checking | store artifacts |
| building | `agent_result` clarification, rounds < max | awaiting_clarification | RecordClarification; `return_state=building`; StartTimer(clarification_sla) |
| building | `agent_result` clarification, rounds ≥ max | escalated | trigger `clarification_limit` |
| building | `agent_result` budget_exceeded | escalated | trigger `budget` |
| checking | `controls_result` passed | reviewing | store results |
| checking | `controls_result` failed, retries < max_auto_retries | building | `auto_retries += 1` |
| checking | `controls_result` failed, retries ≥ max | escalated | trigger `retry_limit` |
| reviewing | `review_result` recommendation | awaiting_sign_off | store recommendation |
| reviewing | `review_result` clarification, rounds < max | awaiting_clarification | `return_state=reviewing`; StartTimer(clarification_sla) |
| reviewing | `review_result` clarification, rounds ≥ max | escalated | trigger `clarification_limit` |
| awaiting_clarification | `clarification_answered` | `return_state` | CancelTimer(clarification_sla) |
| awaiting_clarification | `timer` clarification_sla | escalated | trigger `clarification_sla` |
| awaiting_sign_off | `decide` pass, approvals < min | awaiting_sign_off | RecordSignOff |
| awaiting_sign_off | `decide` pass, approvals = min | closed | RecordSignOff; CloseRun(pass) |
| awaiting_sign_off | `decide` rework | closed | RecordSignOff; CloseRun(rework, cause) |
| awaiting_sign_off | `decide` exception, no pending waiver | awaiting_sign_off | ProposeWaiver |
| awaiting_sign_off | `waiver_decision` approve | closed | DecideWaiver; CloseRun(exception) |
| awaiting_sign_off | `waiver_decision` reject | awaiting_sign_off | DecideWaiver |
| awaiting_sign_off | `decide` terminate | closed | RecordSignOff; CloseRun(terminate) |
| escalated | `escalation_completed` | awaiting_sign_off | store artifacts |
| escalated | `decide` terminate | closed | CloseRun(terminate) |
| any open state except `escalated` | `timer` escalate_after | escalated | trigger `timer`. An escalated run ignores it (FR-021) |
| any automatic state | `step_interrupted`, retries < max | same | `auto_retries += 1` (FR-030a) |
| any automatic state | `step_interrupted`, retries ≥ max | escalated | trigger `retry_limit` |
| any open state | `lifecycle_ended` | closed | CancelAllTimers; CloseRun(terminate): ledger record only, no outcome event (FR-018c) |
| any automatic or waiting state | `event_received` | same | record event in context |

Entering `escalated` also writes the outbox event `T<n>.escalate` (with the trigger) in the same transaction.

Every applied transition also: writes `run.run_transition` and `run.run_activity`, increments
`version`, and cancels timers that no longer apply. `CloseRun` additionally writes the
ledger record and the outbox event in the same transaction, cancels all timers and frees the
active-run slot. When the route is `continue`, the close then starts a `review_due` timer
(FR-018b). That timer is not a signal to this run: when it fires, the timer loop asks the
router to open the next review run of the terminal. Any other timer that fires for a closed
run is ignored.

## Properties (hypothesis, constitution III and IX)

1. No sequence of signals from actors other than `human` ends in `closed` with status pass,
   rework, exception or terminate.
2. `escalated` is only ever entered through an `Escalate` effect from one of the
   orchestrator's own rules. Orchestrator signals can trigger `timer`, `clarification_sla`,
   `retry_limit` and `rework_limit`. An agent can trigger only `clarification_limit` or
   `budget` (what it reported crossed a limit), the reviewer only `clarification_limit`, and a
   human never. No signal can request escalation.
3. `closed` accepts no signal.
4. `clarification_answered` and `escalation_completed` never change `rework_count`.
