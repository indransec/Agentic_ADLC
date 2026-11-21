# Research: Operations Console (019)

Decisions behind [plan.md](plan.md). Each: decision, rationale, alternatives.

## R-01 The mode comes from the API, for every signed-in person

- **Decision**: a new read-only route `GET /board/mode` (any signed-in person) answers
  `{"mode": "console" | "inbox", "board_url": <browser address of the board or null>,
  "can_operate": <the person holds the CoE role>}`. `console` when the API's board settings have
  `ADLC_BOARD_ENABLED=true`. The web app asks once per session at sign-in and again at most every
  60 s (kept in the session); on an error it keeps the last answer, or `inbox` with a notice.
- **Rationale**: one setting decides where people decide (clarification 2026-11-21); the web app
  keeps its boundary (only the API). `/board/health` is CoE-only and heavier.
- **Alternatives**: a web app setting (rejected at the clarification); asking on every rerun
  (a request per click for a value that changes only with a restart).

## R-02 The API needs the board settings in Docker

- **Decision**: the compose file defines the board settings once (`x-board-settings`) and gives
  them to both the `board` and the `api` services; `.env.example` is unchanged (same keys).
- **Rationale**: today only the `board` service receives them, so under compose the API answers
  "disabled" for 016's reconcile and would answer `inbox` for the mode. Found while planning.

## R-03 A run's board item address

- **Decision**: `GET /board/items/{kind}/{object_id}` (any signed-in person; `kind` is `usecase`,
  `run` or `clarification`) answers `{"work_item_id", "url"}` from 016's link table, or 404 when
  the sync has not projected it. The address is built by the adapter (`BoardAdapter.item_url`,
  new): the ADO adapter forms ADO's `{base}/{organization}/{project}/_workitems/edit/{id}` from a
  new setting `ADLC_BOARD_PUBLIC_URL` (the board's address for browsers; defaults to
  `ADLC_BOARD_URL`); the fake board returns a test address.
- **Rationale**: ADO's address shape belongs to the ADO adapter, not the web app (FR-011); inside
  Docker the sync reaches `http://ado-sim:8600` while a browser needs `http://localhost:8600`.

## R-04 The evidence link opens the run page

- **Decision**: the web app's entry routes on the address: when `run` is in the query, it opens
  the Run page (after sign-in if needed; the query survives the sign-in rerun). The evidence URL
  stays `…/?run=` (016's setting).
- **Rationale**: today `/?run=` opens the default page (the inbox), which ignores it.

## R-05 Console navigation

- **Decision**: every page stays registered (old addresses resolve); the mode decides the sidebar,
  the default page and what the decision pages render. Console: Delivery (Use cases, Journey,
  Activity), Insights (Portfolio), Operations (Dead letters, Sync status for operators); the
  default page is Use cases. Inbox, New use case, Clarification, Escalation and Waiver render a
  notice "made on the board" with a link to the board (or to the item when known). Inbox mode:
  as today, plus Sync status for operators.
- **Rationale**: FR-007, FR-008; no broken bookmarks.

## R-06 The run page in console mode

- **Decision**: the decision form's place shows "Decide on the board" with a link to the run's
  work item (R-03), or "not on the board yet" (US1-4). Artifact editing, the review and every tab
  stay.

## R-07 Sync status page

- **Decision**: `views/sync.py`: `GET /board/health` → metrics (last poll and outcome, watermark
  age, outbound pending and oldest age, reverted), a table of refusals by reason, the
  dead-lettered use cases each with "Re-queue" (`POST /board/requeue/{id}`), the last
  reconciliation's differences (`GET /board/reconciliations/{id}`), and "Reconcile now" behind a
  confirmation (`POST /board/reconciliations`). Refreshes at `ADLC_UI_DASHBOARD_REFRESH`. Shown
  only when `can_operate`; when the sync is disabled it says so and offers nothing.

## R-08 Tests

- **Decision**: API tests for the two routes (enabled and disabled, any person, 404); AppTest
  tests through the real API (007 research R-08) with the board enabled by settings and the
  engagement built on the fake board (as 016's API tests do): the deep link, the run page without
  a decision form, the console sweep of every page (SC-002), the sync status page and its actions,
  and inbox mode unchanged (the existing UI suite runs as is, SC-005).

## Dependencies

None new.
