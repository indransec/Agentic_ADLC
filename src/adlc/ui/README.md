# adlc.ui

The web application (feature 007; SA §8): Streamlit, in its own container (`ui`), started with
`streamlit run src/adlc/ui/app.py`. Settings: `ADLC_API_URL` (default `http://api:8000`) and the
host port `ADLC_UI_PORT` (default 8501).

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
| Run | Every SA §8.2 section and the prerequisites (a blocked run says so and why), the artifact editor (up to 1,000 rows; above that read-only with upload offered), spreadsheet upload, attachments, downloads, history, evidence and the decision form. |
| Clarification, Escalation, Waiver | The forms for each request. |
| Dead letters | List with attempts, error and re-queue count; payload and re-queue history on request; re-queue (the API allows the CoE role only). |
| Journey | 013: lanes per terminal, a bar per run, arrows for reworks, reroutes, exceptions, events and re-entry; KPI strip; escalations and exceptions. Refreshes every `ADLC_UI_DASHBOARD_REFRESH`. |
| Activity | 013: the activity feed, filterable by use case, terminal, actor and step; filters survive refreshes. |
| Portfolio | 013: the KPIs across use cases, by risk tier and status. |

## Rendering rules

- Text written by agents or people (intake, comments, reasons, findings, questions, answers, file
  names, artifact cells) is shown only with `st.text`, `st.dataframe` or `st.data_editor`, never
  as Markdown or HTML, and never in a widget label (`tests/integration/ui/test_rendering.py`).
- Markdown is used only for labels the platform writes itself.
- Attachments are offered for download only, never shown inline.
- Every action sends the run version shown on the page; a stale answer reloads the page with a
  message.
