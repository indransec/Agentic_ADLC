# Contract: Agent Runtime

`RuntimeAgentRunner` implements feature 003's `AgentRunner`, and `RuntimeReviewer` implements its
`Reviewer`. The orchestrator wiring (`build_orchestrator`) chooses them; the stubs stay for tests.

## Build attempt

```text
RuntimeAgentRunner.build(context: BuildContext) -> Artifacts | Clarification
                                                 | BudgetExceeded | AttemptFailed
                                                 | ModelUnavailable
```

1. **Resolve the agent.** Find `actors.agent.id` of the pinned spec in the agents catalogue, then
   its prompt (from the registry, by id and version) and its limits (tier defaults with terminal
   overrides).
2. **Build the context pack** (R-06) and hash it.
3. **Run the implementation:**
   - **`stub`:** the existing stub logic returns synthetic artifacts or the scripted result. No
     model is called.
   - **`model`:** loop until the agent produces valid output, a clarification, or reaches a
     limit:
     1. check the limits;
     2. call `gateway.complete` with the time left;
     3. on `unavailable`, return `ModelUnavailable`;
     4. on `refusal`, `truncated` or `request_error`, count a correction; when no corrections
        are left, return `AttemptFailed`;
     5. parse the JSON and validate it (artifacts, or a clarification with `looked_in`). When it
        is invalid, append the correction message and repeat;
     6. on a tool request, call `ToolGate` (authorize first) and append the wrapped result;
     7. return the result.
4. **Validate the output.** Stub output goes through the same check (FR-024). A stub that returns
   output that does not fit gives `AttemptFailed`.
5. **Record the attempt.** Write one `run.agent_attempt` row (outcome, hashes, totals, limit
   reached) and one `adlc.agent.build` span.

## Review attempt

```text
RuntimeReviewer.review(context: ReviewContext) -> Recommendation | Clarification
                                                | AttemptFailed | ModelUnavailable
```

The review follows the same loop, with the reviewer agent from the catalogue and the `reasoning`
tier.

- **Input:** only what `ReviewContext` carries, plus the prerequisite evidence (FR-016).
- **Output:** the reviewer schema (R-09).
- **Recommendation:** `Recommendation(status, checklist_scores, findings as "item: text",
  reason, root_cause, reviewer="model")`.

`ADLC_REVIEWER_MODE=stub` selects `StubReviewer`, wrapped so the attempt is still recorded with
`implementation = stub`.

## Engine responsibilities (feature 003 changes)

- **Connections:** the engine reads the step's inputs, then releases its database connection
  before calling `build` or `review` (R-07).
- **`ModelUnavailable`:**
  - while the outage is under the limit, record a `deferred` activity, set
    `model_unavailable_since` if empty, and lease the run until now plus the back-off. No signal
    is sent.
  - once over the limit, send the `model_unavailable` result signal.
- **`AttemptFailed`:** send the `failed` result signal.
- **Any other result:** clear `model_unavailable_since`.

## Tool gate

```text
ToolGate.call(run_id, usecase_id, terminal_id, tool, arguments)
  # action and resource come from the tool binding's declared permission ("action:resource")
  -> ToolOutput(text) | ToolRefused(reason)
```

`authorize(f"agent:{run_id}", action, resource, EvalContext(terminal_id, f"tool:{tool}", run_id,
usecase_id))` is called before every call. A refusal is returned to the agent and the call is not
made. The output is wrapped as `<data source="tool:{tool}">`.
