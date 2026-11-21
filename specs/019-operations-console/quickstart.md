# Quickstart: Operations Console (019)

Contracts: [api-and-pages](contracts/api-and-pages.md).

## 1. Checks

```bash
uv run pytest tests/integration/ui tests/integration/api/test_board_routes.py tests/unit
make ado-sim-check   # unchanged
```

## 2. Walk it

1. Start the platform with the board sync enabled (016's quickstart) and the web app.
2. Sign in to the web app as an approver: the sidebar shows the console (no Inbox, no New use
   case); the default page is Use cases.
3. On the board, open a run item awaiting sign-off and follow its evidence link: the console opens
   on that run (after sign-in if needed), with the evidence and "Decide on the board" linking back
   to the item.
4. Open the old inbox address: the notice points to the board.
5. Sign in as the CoE: Sync status shows the health; stop the simulator: the poll outcome and the
   watermark age change; start it again; "Reconcile now" shows the differences.
6. Set `ADLC_BOARD_ENABLED=false`, restart the API: the web app is the inbox again.

## Results

Walked live on 2026-11-21 (T015), macOS, Python 3.12. Real processes: the simulator (`ado-sim
serve`), the board sync (`adlc-board run`) and the platform API (`adlc-api`), the last two with
the board sync enabled and the board settings the compose file now gives both. The orchestrator
ran in the walking script with stub agents, drained in real time. No browser was available: the
web app was driven by Streamlit's AppTest against the live API (a real session per person, real
sign-in). All 10 steps passed.

| Step | Result |
| --- | --- |
| A run on the board | the Business Owner created an Epic on the board's page; it became UC-0001 with its T0 run item, whose evidence link is `http://localhost:8501/?run=UC-0001%2FT0%2Frun-1` |
| 2. The console | sign-in lands on Use cases; the sidebar lists Use cases, Journey, Activity, Portfolio, Dead letters (no Inbox, no New use case) |
| 3. The evidence link | opened with the link's `run`, the new session signs in and lands on the Run page of UC-0001/T0/run-1: Artifacts, Reviewer recommendation, Control results, and Decision with "Decide on the board" linking to the run's work item (`…/_workitems/edit/2`); the simulator answers that address with its sign-in, then the item; no decision form |
| 4. The inbox's address | "Sign-offs, decisions, clarifications, waivers and escalations: made on the board now." with "Open the board" |
| 5. Sync status | the CoE's sidebar adds Sync status; Last poll ok, watermark age 11 s, nothing pending or dead-lettered |
| 5. The board stopped | the simulator stopped: the page showed Last poll `board_unreachable` 8.9 s later; started again: `ok` 9.4 s later (SC-003: one poll interval plus the page's refresh) |
| 5. Reconcile now | after the confirmation: "Outcome ok: 2 items checked, 0 created, 0 differences", well under a second (SC-004: 10 s) |
| 6. The inbox back | the API restarted with `ADLC_BOARD_ENABLED=false`: a new session lands on the Inbox, with Inbox and New use case in the sidebar |

The layout at 1280×720 in a browser is part of the demo rehearsal (feature 020).
