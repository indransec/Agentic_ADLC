# Contract: Pages, addresses and rendering (the web application)

The page registry (`web/src/nav/registry.ts`) is the single source of this table (FR-002).
Behaviour per page is today's, as described in `src/adlc/ui/README.md` on this branch (FR-001).

| Id | Title | Section | Sidebar | Path and query | API reads | API actions |
| --- | --- | --- | --- | --- | --- | --- |
| `sign-in` | Sign in | — | no | `/sign-in?next=` | — | `POST /auth/sign-in` (cookie) |
| `inbox` | Inbox | Work | yes | `/inbox` | `GET /inbox`, `GET /changes`, `GET /events/proposed` (every 30 s and on demand) | change decision, proposed-event decision |
| `new-use-case` | New use case | Work | yes | `/usecases/new` | — | `POST /usecases` |
| `use-cases` | Use cases | Delivery | yes | `/usecases?mine=1&usecase=` | `GET /usecases`, `GET /usecases/{id}` | `POST /usecases/{id}/verify` |
| `journey` | Journey | Delivery | yes | `/journey?usecase=` | journey, KPIs (every dashboard interval) | — |
| `activity` | Activity | Delivery | yes | `/activity?usecase=&terminal=&actor=&step=` | `GET /dashboard/activity` (every dashboard interval) | — |
| `portfolio` | Portfolio | Insights | yes | `/portfolio` | `GET /dashboard/portfolio` | — |
| `dead-letters` | Dead letters | Operations | yes | `/dead-letters?event=` | `GET /dead-letters`, `GET /dead-letters/{id}` | `POST …/requeue` (CoE) |
| `run` | Run | — | no | `/run?run=` | `GET /runs/{id}`, history, timeline, attachments | decision, artifact save, spreadsheet upload, attachment |
| `clarification` | Clarification | — | no | `/clarification?run=&id=` | `GET /runs/{id}` | `POST /clarifications/{id}/answers` |
| `escalation` | Escalation | — | no | `/escalation?run=` | `GET /runs/{id}` | `POST /runs/{id}/escalation` |
| `waiver` | Waiver | — | no | `/waiver?run=&id=` | `GET /runs/{id}` | `POST /waivers/{id}/decision` |

## Redirects

- `/` → `/run?run=<id>` when `?run=` is present (old evidence links); otherwise `/inbox`.
- Any page without a session → `/sign-in?next=<path and query>`. After sign-in, `next` is followed
  only if it is a relative path starting with a single `/`; otherwise `/inbox`.
- An unknown path shows a "page not found" state with a link to the Inbox.

## Shell

- **Sidebar:** the logo, the environment badge (from `/config.json`), the sections in registry
  order, the person's display name and roles, and sign-out.
- **Theme:** today's neutral light theme, system fonts and one accent colour, with the status
  colours ported from `render.STATUS_COLOURS` into `web/src/ui/status.ts`.

## Rendering rules (FR-010 to FR-012, research R-11)

- **Agent and person text** goes only through `<Literal>` (text node, `pre-wrap`, wraps long
  words) or AG Grid text cells (the default text renderer). Never into a label, `aria-label`,
  `title`, placeholder or option label, and never into Markdown or HTML. This covers intake,
  comments, reasons, findings, questions, answers, file names and artifact cells.
- **Selection lists of agent or person items** (Inbox, Dead letters) show platform-written
  labels such as the kind, id and time. The person-written text appears beside them in a
  `<Literal>`.
- **`<StatusBadge value>`** shows the platform's word and colour only for values in the known
  status list (states, outcomes, statuses, risk tiers, from today's `render.STATUS`). Any other
  value is plain text.
- **Attachments** are offered as "Download" buttons only (R-11).
- **Decision form:** built only from `run.form`: outcomes, `root_causes`, `target_terminal_for`,
  `target_terminals`, `requires`, `typed_fields`, `alternatives`, `reason_required_unless`,
  `can_decide`, `can_terminate`, `controls_pending` and `waiver_pending`. No outcome, terminal or
  role value appears in code (constitution I).
- **Artifact editor:** editable when the run allows editing and the table has at most 1,000 rows
  (cells editable, rows can be added and removed). Above that it is read-only, with spreadsheet
  upload offered. Every save sends `expected_version` (R-08).
- **Errors:** shown as "The platform refused this: <kind in words>" plus the detail as literal
  text. A `field` error is shown beside that field.

## Accessibility (FR-028)

- Every control has a visible label (platform words only).
- The keyboard order follows the page.
- A status is shown as both a word and a colour.
- Focus moves to the page heading on navigation.
- `@axe-core/playwright` finds no serious or critical violations on any page.
