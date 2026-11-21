# Contract: how a board change becomes a request

Pure rules in `engagement/classify.py` and `engagement/inputs.py` (R-05, R-10), applied in order
for each update read (R-04). Names in quotes are mapping keys, not literals in code.

## 1. Who changed it

| Changer | Result |
| --- | --- |
| the service account | `own`: recorded, nothing else |
| a board user with no account whose `board_identity` matches | every request in the update is refused `not_mapped`; platform-written changes are reverted |
| a mapped account | continue with its account name and roles |

## 2. What changed

| Item | Change | Action |
| --- | --- | --- |
| any linked item | a `platform_written` field | revert to the platform's value, comment the rule (`platform_field`) |
| unlinked item of the `usecase` type in `area` | created, or title or description changed | `register_usecase` (title → name, description as plain text → intake text) |
| linked `run` item | `decision.field` set to a non-empty value | `decide` with that value |
| linked `clarification` item | `answer` field set to a non-empty value | `answer` |
| anything else | | `ignored` |

A Removed or Closed linked item, or one whose use case is closed, refuses any request (`closed`).

## 3. Reading a decision (`decide`)

At the update's revision (`get_at`):

1. The value must be one of `decision.values`; else `unknown_value` (the reply lists the values).
2. Platform action by value: `pass | rework | exception | terminate` → sign-off decision on the
   run; `approve_waiver | reject_waiver` → the run's pending waiver; `complete_escalation` → the
   escalated run.
3. Inputs: each input the action needs (from the run's decision form) from its field; if the field
   is empty, from a comment line `<label>: <value>` (`value <name>: <v>` for values). The rest of the
   comment is the comment. A field and a differing line → the field, and the reply says so.
4. Checked against the form before the call: root cause in the form's causes, rework target in its
   terminals, values of the declared type; else `invalid_input` naming the input and what is
   allowed; a missing required input → `missing_input`.

## 4. Applying it

`OrchestratorService` call (R-06) as the mapped actor, with `source`. Exceptions → reason codes:

| Exception | Code |
| --- | --- |
| `NotAuthorised` | `not_authorised` |
| `InvalidDecision` | `invalid_input` |
| `InvalidTransition`, `StaleRun` (after one retry), `UnknownRun` | `stale` |
| `AlreadyAnswered` | `already_answered` |

## 5. Replying

| Outcome | Board writes (service account) |
| --- | --- |
| accepted | comment `ADLC: <action> by <display name> accepted`; the projector then shows the result and clears the decision, input and answer fields (R-09) |
| refused | the request field (the decision, or the answer) cleared if it still holds this update's value; the comment and inputs stay so the person can complete them and decide again; comment `ADLC: refused — <reason>` (changed during T041: restoring the previous value could bring back an earlier refused request) |
| ignored | nothing |
| registration refused (`invalid_usecase`, or `not_mapped`) | comment on the Epic with the reason; the Epic is left as is (an edit is a new request) |

Answers: the answer field split into numbered lines (`1.`, `2.` …) or, for a one-question round,
the whole text; the count must equal the questions (`invalid_input`).
