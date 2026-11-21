# adlc.ui

The web application (feature 007; SA §8): Streamlit, in its own container (`ui`), started with
`streamlit run src/adlc/ui/app.py`. Settings: `ADLC_API_URL` (default `http://api:8000`), the
host port `ADLC_UI_PORT` (default 8501) and `ADLC_ENV` (shown as a badge when set).

## Look and layout

- Theme: `.streamlit/config.toml` at the repository root (Streamlit reads it from the working
  directory; the image copies it). A neutral light theme, system fonts, one accent colour.
- Navigation: `st.navigation` with the sidebar drawn by `app.py` in sections (Work, Delivery,
  Insights, Operations). Run, Clarification, Escalation and Waiver are opened from other pages,
  never from the sidebar. A page opens another with `render.navigate(title, ...)`.
- The page modules live in `views/`, not `pages/`: Streamlit treats a `pages/` folder beside the
  main script as file pages of its own.
- Shared pieces are in `render.py` (page header, status badges, tables, the open control, errors)
  and `format.py` (times in UTC, durations, money, column names). Status colours are defined once
  (`render.STATUS`, `render.STATUS_COLOURS`) and match the theme and the charts.

## Boundary

The application calls only the platform API, through `client.ApiClient`. The bearer token lives in
the Streamlit session state on the server, never in the browser. Modules here import only
`adlc.ui` and `adlc.config` from the platform (`tests/unit/test_ui_boundary.py`). Hiding an action
the person may not take is a convenience; the API enforces every rule.

## Pages

| Page | What it does |
| --- | --- |
| Sign-in | Account and password. Sign-out, or an expired session, clears the token and returns here. |
| Inbox | Items waiting for the person, refreshed every 30 s and on demand; opens each on its page. |
| New use case | The intake form. |
| Use cases | "Only mine" or all, the journey (runs with times and cost), ledger verification. |
| Run | A summary bar (run, terminal, state, due, cost); the artifacts beside the reviewer recommendation, control results and decision form; the other SA §8.2 sections as tabs (prerequisites, citations, prior rework, clarifications, approvals, waiver, activity, timeline, evidence). A blocked run says so and why; the artifact editor takes up to 1,000 rows (above that read-only with upload offered). The run is kept in the address (`?run=`). |
| Clarification, Escalation, Waiver | The forms for each request. |
| Dead letters | List with attempts, error and re-queue count; payload and re-queue history on request; re-queue (the API allows the CoE role only). |
| Journey | 013: lanes per terminal, a bar per run, arrows for reworks, reroutes, exceptions, events and re-entry; KPI strip; escalations and exceptions. Refreshes every `ADLC_UI_DASHBOARD_REFRESH`. |
| Activity | 013: the activity feed, filterable by use case, terminal, actor and step; filters survive refreshes. |
| Portfolio | 013: the KPIs across use cases, by risk tier and status. |
| Sync status | 019: the board sync's health (last poll, watermark age, pending and dead-lettered board deliveries, refusals by reason, reverts), the last reconciliation's differences, "Reconcile now" behind a confirmation, and re-queue of a board delivery. Offered only to the people who operate the sync (the API's answer, the CoE role). |

## Inbox or operations console (feature 019)

The web app is the **operations console** when the board sync is enabled (`ADLC_BOARD_ENABLED`),
and the **inbox** otherwise. It does not choose: it asks the API (`GET /board/mode`) at sign-in and
again at most every 60 s (`adlc.ui.mode`), and keeps the last answer if the API cannot be asked
(the sidebar says so). Turning the sync off and restarting the API brings the inbox back.

In console mode people decide on the board. The sidebar lists Use cases (the start page), Journey,
Activity, Portfolio, Dead letters and, for operators, Sync status. Inbox, New use case,
Clarification, Escalation and Waiver stay registered (old addresses resolve) but say the action is
made on the board, with a link to it. The Run page keeps every evidence section and artifact
editing before sign-off; in place of the decision form it links to the run's board item ("Decide
on the board", `GET /board/items/run/{run_id}`), or says the run is not on the board yet.

The board's evidence link (`ADLC_BOARD_EVIDENCE_URL`, `…/?run=<run id>`) opens the Run page on that
run, after sign-in (a link always opens a new session).

## Rendering rules

- Text written by agents or people (intake, comments, reasons, findings, questions, answers, file
  names, artifact cells) is shown only with `st.text`, `st.dataframe` or `st.data_editor`, never
  as Markdown or HTML, and never in a widget label (`tests/integration/ui/test_rendering.py`).
- Markdown is used only for labels the platform writes itself. A status badge shows the
  platform's own word for a known state, outcome, status or risk tier; any other value is plain
  text.
- Attachments are offered for download only, never shown inline.
- Every action sends the run version shown on the page; a stale answer reloads the page with a
  message.
