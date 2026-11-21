# Implementation Plan: Operations Console

**Branch**: `019-operations-console` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-operations-console/spec.md` (Gate 1 approved
2026-11-21)

## Summary

The web app (Streamlit, feature 007) becomes an operations console when the board sync is
enabled, and stays the inbox when it is not. It learns the mode from a new read-only API answer
(`GET /board/mode`), so one setting decides where people decide. In console mode the sidebar lists
only the console's pages, the decision pages point to the board, and the run page (opened from the
board's evidence link, which now routes to it) shows the evidence and artifact editing with
"Decide on the board" linking to the run's work item (`GET /board/items/{kind}/{id}`, the address
built by the adapter from a new `ADLC_BOARD_PUBLIC_URL`). A Sync status page shows 016's health
for the CoE, with reconcile now and re-queue. Compose gives the API the board settings it lacks
today. Every API command is unchanged.

## Technical Context

**Language/Version**: Python 3.12, the platform's uv project.

**Primary Dependencies**: as today (FastAPI, Streamlit); no new dependency.

**Storage**: no new table; reads 016's link table and sync health.

**Testing**:
- **API (test first)**: `/board/mode` (enabled, disabled, any signed-in person, `can_operate`);
  `/board/items/...` (found, not yet projected, unknown kind, disabled, a run id with `/`).
- **Adapter**: `item_url` of the ADO adapter (public URL, organisation and project quoted) and of
  the fake board; settings default and validation of `ADLC_BOARD_PUBLIC_URL`.
- **Web app (AppTest through the real API)**: the deep link (signed in and after sign-in); the
  run page in console mode (no decision form, the board link, "not on the board yet"); the
  console sweep of every page (SC-002); the notices of the removed pages; Sync status (metrics,
  refusals, re-queue, reconcile now with confirmation, disabled, not offered to others); the mode
  re-read and the API-error fallback; inbox mode: the existing UI suite unchanged (SC-005).
- **Deployment**: the env-example and compose tests cover the API's board settings and the new key.

**Target Platform / Project Type**: the platform's web app and API (desktop browsers).

**Performance Goals**: the run page from the link in under 3 s (SC-001); reconcile now in under
10 s for the demo (SC-004).

**Constraints**: the web app calls only the API (boundary test); agent and person text as plain
text; no board address, organisation or project in code.

**Scale/Scope**: the demo (tens of use cases).

## Constitution Check

| Article | How this plan complies |
| --- | --- |
| I, II Spec-driven, no values | the board's addresses and names are settings; ADO's address shape is in the ADO adapter |
| III Agents build, humans decide | decisions stay with people, on the board; the console shows the evidence they rest on |
| IV Separation of duties | unchanged: every command keeps its rights checks; sync operation stays CoE-only |
| V Evidence-first | the evidence link opens the run's evidence before a sign-off (SA §8.2) |
| VII Interfaces | `item_url` added to the `BoardAdapter` port; the web app still talks only to the API |
| IX Test first | the API routes and the adapter addition are test first |
| XI Secure | read-only additions behind sign-in; operation behind the CoE role; no secret in answers |
| XII Simplicity | the mode is derived, not configured; pages stay registered and render notices |

**Result: pass.**

## Project Structure

```text
src/adlc/api/routes/board.py     GET /board/mode, GET /board/items/{kind}/{object_id:path}
src/adlc/config/settings.py      BoardSettings.board_public_url
src/adlc/engagement/port.py      BoardAdapter.item_url
src/adlc/engagement/ado.py       item_url (ADO's edit address)
src/adlc/engagement/fake.py      item_url (a test address)
src/adlc/ui/app.py               the mode, the sidebar and default per mode, the ?run= route
src/adlc/ui/mode.py              reading and keeping the mode (new)
src/adlc/ui/views/run.py         "Decide on the board" in console mode
src/adlc/ui/views/sync.py        Sync status (new)
src/adlc/ui/views/moved.py       the notice for pages now on the board (new)
deploy/compose.yaml              x-board-settings for board and api; ADLC_BOARD_PUBLIC_URL
.env.example                     ADLC_BOARD_PUBLIC_URL
tests/integration/api/test_board_routes.py, tests/unit/engagement/…, tests/integration/ui/test_console.py, test_sync_status.py
docs: src/adlc/ui/README.md, deploy/README.md, docs/run-without-docker.md
```

## Complexity Tracking

None.
