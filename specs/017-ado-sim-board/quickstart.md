# Quickstart: ADO Simulator Board (017)

Contracts: [pages](contracts/pages.md), [commands](contracts/cli-settings-seed.md); data:
[data-model](data-model.md).

## 1. Checks

```bash
make ado-sim-check     # includes the page tests, the session sweep, escaping, a11y checks, timing
```

## 2. Run it

```bash
cd ado_sim
export ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db ADO_SIM_TOKEN_KEY=...   # as in 015
uv run ado-sim migrate && uv run ado-sim seed --if-new --file seed/demo.yaml
uv run ado-sim password set --all          # one rehearsal password for every demo user
uv run ado-sim serve                       # http://127.0.0.1:8600/
```

## 3. Walk it

1. Open `http://127.0.0.1:8600/` → the sign-in page lists the demo users (not the service account).
2. Sign in as the product owner with the page password; then sign out and sign in with a personal
   access token; a wrong credential gives one message (US1).
3. The board: one column per Epic state, Closed and Removed collapsed (US2).
4. Create an Epic "Claims triage" in `Agentic ADLC\Use cases` → its card appears; its page shows it
   created by the product owner (US4, SC-003).
5. Change its state and sub-stage through the API (as the platform does) → the card moves within
   5 s, no reload (US3, SC-002).
6. Filter on an area; reload → the filter stays (US5).
7. With the platform's `board` process enabled (016), the new Epic becomes a use case and moves to
   the first terminal's column on its own (SC-006).

## Results

Walked live on 2026-11-21 (T037), macOS, Python 3.12: the simulator's own process (`ado-sim
serve`, scratch database, port 18601), driven over HTTP with a real session cookie, page passwords
set with `ado-sim password set --all --stdin`, and the platform-style change made through the API
with the service account's token. Every step behaved as specified.

| Step | Result |
| --- | --- |
| 1. Open `/` | `303` to `/_signin?next=%2F`; the sign-in page offers the 15 demo users, not the service account. (The walking script's own check wrongly expected a second redirect here; the behaviour observed is the one specified.) |
| 2. Sign in | page password: `303` back to the board, session cookie set `HttpOnly`; a personal access token signs in the engineering lead; a wrong password answers `400` with the single refusal message |
| 3. The board | 12 columns (the Epic states in process order), Closed and Removed collapsed; the content security policy header is sent |
| 4. Create an Epic | "Claims triage" in `Agentic ADLC\Use cases`, created by Product Owner (from the API's view of item 1) |
| 5. An API change | after a PATCH of state and sub-stage with the service account's token, the next poll of the columns shows the card in the T1 column with "Awaiting sign-off" |
| 6. Filter | the area is in the page address and in the poll URL |
| Sign out | the session ends; the board asks for sign-in again |

Measured by `make ado-sim-check` with 200 Epics: the board page and its refresh at the 95th
percentile in 2.4 ms and 2.2 ms (SC-001: 1 s and 0.5 s). The 1280×720 layout and the full
board-to-platform loop of SC-006 need a browser and the platform's `board` process (016); they are
part of the demo rehearsal (feature 020).
