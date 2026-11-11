# adlc.inbox

The read side of the human inbox (feature 007; SA §8). It answers "what is waiting for me?",
builds the run detail and decision form, and holds the role rules that the operations share.
Nothing here is stored: every answer is derived from the tables of features 003, 005 and 006.
Specification: `specs/007-human-inbox/`.

## Modules

| Module | Purpose |
| --- | --- |
| `rules.py` | Who may act. Still-needed sign-off roles (rule roles and required conditional roles, minus those already approved), clarification addressee, accountable roles, waiver approvers (the spec's `exception` set-by roles, else the accountable roles), artifact editors, CoE. `OrchestratorService` and `LedgerService` use the same functions, so an inbox item never offers an action the operation would refuse. |
| `forms.py` | `build_form`: the decision form from the pinned spec. Outcomes from `status_rights.human` (minus disabled routes), required fields per outcome, root causes from the rework routes (and which need an owning terminal), values a pass emits that no artifact supplies, alternatives, the reviewer's recommendation (a different decision needs a reason), and whether the person may decide, terminate, edit or complete an escalation. |
| `service.py` | `InboxService`: use cases ("mine" means submitted, or holding a role in one of its runs' terminals), the journey (runs, the 005 summary, the 006 cost), inbox items, the run detail, attachment lookup. |

## Inbox items

Each item has `kind`, `id`, `usecase_id`, `terminal_id`, `run_id`, `role`, `title`, `arrived_at`,
`due_at` and `controls_pending`. The list is ordered soonest due first, then by arrival; items with
no due time come last.

| Kind | Shown to |
| --- | --- |
| `sign_off` | Runs awaiting sign-off where the person holds a still-needed role and has not approved. |
| `clarification` | Unanswered rounds addressed to a role the person holds. |
| `escalation` | Escalated runs whose terminal's accountable role the person holds. |
| `waiver` | Pending waivers the person may approve and did not propose. |
| `dead_letter` | Dead-lettered events, for the CoE role (`ADLC_DEADLETTER_ROLE`) only. |

## Run detail

The run detail is `InboxService.detail`; there is no separate `RunDetailService` (task T017 named
one, but the detail shares the inbox's queries and rules, so it stays in one service). It returns every SA §8.2 item: the run (state, version, `controls_pending`),
artifacts with columns, rows, current version and attachments, control results, the reviewer's
recommendation with the checklist item text and scores, prior rework comments (this terminal's
earlier runs in the use case that closed as rework, newest first), clarifications, approvals that
still count, the pending waiver, the timer, the cost, the activity timeline, checks, checklist
results, the ledger record and `form`.
