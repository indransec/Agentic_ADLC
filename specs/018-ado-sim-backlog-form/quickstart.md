# Quickstart: ADO Simulator Backlog and Work Item Form (018)

Contracts: [pages](contracts/pages.md); data: [data-model](data-model.md).

## 1. Checks

```bash
make ado-sim-check     # form, backlog, sanitiser property tests, conflicts, a11y, timing
uv run pytest tests/contract/board   # the decision values of the seed and the tracker mapping agree
```

## 2. Walk it (with 016's sync running, as in 016's quickstart)

1. Sign in as the business owner; create an Epic from the board → it becomes a use case.
2. Open the backlog → the Epic with its T0 run item beneath it.
3. Open the run item's form → the description lists the decision values; the evidence link opens
   the run in the console.
4. As an approver, choose Pass in the decision list, comment, type `risk_tier: medium` in Values,
   save → history shows the change; within the poll interval a comment "accepted" appears and the
   Epic moves to T1 (US1).
5. Open the Epic's form, change its state to a later stage, save → the platform sets it back with
   a comment (US5, D-12).
6. Open the same form in two tabs, save in both → the second gets the conflict and keeps its values.
7. When T2 asks, answer its clarification item in the answer field → the run continues (US2).

## Results

Walked live on 2026-11-21 (T023), macOS, Python 3.12. Real processes: the simulator (`ado-sim
serve`, scratch database, port 18602) and the board sync (`adlc-board run`, port 18052), talking
over HTTP. The platform's database was a scratch copy with the specs registered; its orchestrator
ran in the walking script with stub agents (T2's agent asks one clarification), drained in real
time. Accounts carried `board_identity` = the simulator's demo users. Every person acted only
through the pages, over HTTP, with their own session cookie and CSRF token: no inbox, no API calls
on a person's behalf (SC-006). All 12 steps passed.

| Step | Result |
| --- | --- |
| 1. Register from the board | the Business Owner created "Claims triage" in `Agentic ADLC\Use cases` with the board's form; it became UC-0001 9.1 s later |
| 2. The backlog | the Epic with its T0 run item beneath it |
| 3. The run item's form | the decision list offered the mapping's values; the description listed what each needs and "Waiting for: business_owner"; the evidence link opened the run in the console |
| 4. Sign-off from the form | Pass, comment and `risk_tier: medium` in Values, saved by the Business Owner; accepted 9.7 s after the save; the Epic moved to T1; the decision and comment are in the run item's history as the Business Owner's |
| 5. A platform field (D-12) | the Product Owner set the Epic's state to T5 on its form; set back to T1 9.9 s after the save, with the comment "ADLC: System.State is set by the platform; changed back." |
| 6. A conflict | two people opened the T1 run item's form; the first save `303`, the second `412` with its value kept; the stored value was the first |
| 7. T1 and the clarification | T1 signed off from the form by the Business Owner and the Product Owner (each accepted in under 10 s); at T2 the clarification item (a Task under the run) showed the numbered questions; the Engineering Lead's answer on its form was accepted 9.7 s later, the answers stored as theirs, and the run continued to awaiting sign-off |
| The backlog after | the Epic with its T0, T1 and T2 run items and the clarification beneath |

Every board change was acted on within one poll interval (about 10 s). SC-001 (a sign-off in under
a minute): opening the form, choosing Pass, typing the comment and the value and saving takes well
under a minute, and the platform's answer follows within the poll interval. The 1280×720 layout
needs a browser and is part of the demo rehearsal (feature 020).

Found during the walk (both outside this feature):

- **Feature 016, a fault:** a typed value the platform's database refuses (the first attempt typed
  `risk_tier: risk_tier (typed)`, the placeholder of the test helper, not `low`, `medium` or
  `high`) is not refused with a comment: the sync logs "could not be handled; the watermark stays"
  and retries that update on every poll, and every later board change waits behind it. Fixed on
  2026-11-21 in two places: the orchestration service refuses a pass whose `risk_tier` is not one
  of the policy's tiers (an invalid decision, so the board gets a comment and the inbox a refusal),
  and the sync carries on with the other items when one fails, keeping the watermark for it (016
  research R-04). Tests: `test_an_unknown_risk_tier_is_refused`,
  `test_an_invalid_typed_value_is_refused_with_a_comment`,
  `test_a_failing_item_does_not_hold_back_the_others`.
- **Feature 017, a usability point:** the board's create form defaults to the filtered area, or the
  first one (`Agentic ADLC`); only Epics in the mapping's area (`Agentic ADLC\Use cases`) are
  registered, so an Epic created in the root area is silently left alone.
