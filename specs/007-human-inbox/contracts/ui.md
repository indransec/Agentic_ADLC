# Contract: Web Application (feature 007)

The Streamlit process uses only the API operations in [api.md](api.md). Its pages:

| Page | Shows | Actions |
| --- | --- | --- |
| Sign in | — | Sign in; sign out from every page |
| Inbox | Items of `GET /inbox`, grouped by kind; due times; "controls being re-run" | Open the item; refresh every 30 s and on demand |
| New use case | Intake form | Submit, then open its journey |
| Use cases | My use cases, or all; journey per use case (runs with state, status, times, cost) | Open a run; verify the ledger |
| Run detail | Everything in SA §8.2 (spec FR-008): artifacts with version, producer and attachments; control results; reviewer recommendation with item text, scores, findings, reason and root cause; prior rework comments; clarifications; approvals; timer; cost; timeline | Decide (form from `form`); edit tables; upload a spreadsheet; attach a file; download attachments; view version history |
| Clarification | Questions, who asked, where they looked | Answer |
| Escalation | Artifacts as editable tables | Complete, which sends the run to sign-off |
| Waiver | Proposal fields and proposer | Approve or reject, with a comment |
| Dead letters (CoE) | Dead-lettered events | Requeue |

## Rules

- **Plain text only.** Free text from agents and people is rendered only as plain text: comments,
  findings, intake, clarification answers, and artifact cells (research R-07).
- **Hide what is not allowed.** Actions a person may not take are hidden or disabled, based on the
  detail's `form.can_decide` and `form.can_edit`. The API remains the authority.
- **Carry the version.** Every action sends the `version` it was made on. A `stale` answer
  reloads the page and tells the person.
- **Show errors plainly.** Errors are shown with their `detail`, never as a stack trace.
