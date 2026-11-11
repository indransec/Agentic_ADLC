# Implementation Plan: Human Inbox

**Branch**: `007-human-inbox` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-human-inbox/spec.md`

## Summary

The platform API gains the human operations of SA §8. A Streamlit web application in its own
container uses only those operations.

**API (`src/adlc/api/routes/`):**
- use cases and journeys;
- the inbox, from a new `InboxService` (`src/adlc/inbox/`);
- run detail with a decision form built from the pinned spec;
- decisions, clarification answers, waiver decisions and escalation completion;
- artifact edits, spreadsheet uploads and attachments, with download-only serving;
- ledger verification and dead letters.

The API calls the existing services of features 003, 005 and 006, so every action keeps its role
checks, activity records, sign-off rows and ledger effects. Errors have one shape. Decisions and
edits carry the run version.

**Web application (`src/adlc/ui/`):** sign-in, inbox, intake, use cases and journey, run detail
with sign-off and the artifact editor, clarification, escalation and waiver forms, and dead
letters. All text from agents and people is rendered as plain text. Notifications are in-app only.

## Technical Context

**Language/Version**: Python 3.12 (existing `adlc` package, uv, mypy strict, ruff)

**Primary Dependencies**:

- **Already used:** FastAPI, uvicorn, SQLAlchemy, the feature 003–006 services.
- **New:**
  - `streamlit==1.66.1` (Apache-2.0);
  - `httpx` moves from the dev dependencies to the main ones (BSD-3);
  - `python-multipart` (Apache-2.0) for uploads.

**Storage**: none new (data-model.md). No migration.

**Testing**: pytest.

- **Unit:** inbox rules, form building, error mapping, download headers.
- **Integration (API):** every operation through FastAPI's test client on the orchestration
  harness, with role and stale cases.
- **UI:** `streamlit.testing.v1.AppTest` with an `httpx` client over an ASGI transport to the
  real app, so pages are exercised end to end through the API.
- **Scenario:** the sample lifecycle driven through the API only.

**Target Platform**: two processes in Docker Compose. `api` (existing) and the new `ui`
(Streamlit, port 8501 inside, `ADLC_UI_PORT` outside).

**Project Type**: web service and web application inside the platform package.

**Performance Goals**: inbox and run detail under 1 s for MVP volumes; an approver decides in
under 2 minutes (SC-007).

**Constraints**:

- **Sessions:** every operation needs a session (FR-001).
- **No database from the UI** (FR-020).
- **Plain text:** no Markdown or HTML rendering of agent or person text.
- **Downloads only** for attachments.
- **No terminal-specific code** (constitution I).

**Scale/Scope**: tens of people, tens of open runs, one organization.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| streamlit 1.66.1 | Web application (build plan stack) | Apache-2.0 |
| httpx (now runtime) | The UI's API client | BSD-3-Clause |
| python-multipart | Multipart uploads in FastAPI | Apache-2.0 |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Forms, outcomes, root causes, fields and artifact columns come from the pinned spec; the scan covers `api/`, `inbox/` and `ui/` | Pass |
| II Superset, not values | No values are decided in the UI; it shows what the spec and services give | Pass |
| III Agents build, humans decide | Every decision is a person's, through the service; the reviewer's recommendation is shown as advice, and a different decision needs a reason | Pass |
| IV Separation of duties | Role checks stay in the services; the inbox uses the same rules; waiver proposers cannot approve | Pass |
| V Evidence-first | Every action records activity and sign-off through the services; the ledger stays verifiable; verification is in the app | Pass |
| VI Deterministic first | No judgement in the API or UI | Pass |
| VII Interfaces | One API for every channel; the UI is a client of it | Pass |
| VIII Open source | Streamlit, httpx, python-multipart | Pass |
| IX Test first | Inbox rules, the form builder and error mapping are written test-first | Pass |
| X Observable | API spans carry account, run and use case | Pass |
| XI Secure | Sessions everywhere; download-only attachments with strict headers; plain-text rendering; XSRF on; no request bodies in logs | Pass |
| XII Simplicity | No new tables; the inbox is derived; in-app notifications only | Pass |
| XIII Naming | Paths and fields follow Annex A | Pass |

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/007-human-inbox/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── api.md     # operations, bodies, answers, errors
│   └── ui.md      # pages, actions, rendering rules
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/adlc/inbox/
├── __init__.py  README.md
├── rules.py      # who may act: sign-off, clarification, escalation, waiver, CoE (shared with services)
├── service.py    # InboxService.items(person); RunDetailService.detail(run_id, person)
└── forms.py      # decision form from the pinned spec
src/adlc/api/
├── app.py        # builds runs, OrchestratorService, LedgerService, InboxService once
├── errors.py     # exception → status and kind (R-05)
├── deps.py       # current actor, services
└── routes/{usecases,inbox,runs,artifacts,clarifications,waivers,dead_letters}.py
src/adlc/ui/
├── app.py        # Streamlit entry: sign-in and navigation
├── client.py     # ApiClient (httpx), error type, injectable for tests
├── render.py     # plain-text helpers; tables; download buttons
└── pages/{inbox,intake,usecases,run,clarification,escalation,waiver,dead_letters}.py
src/adlc/orchestration/service.py   # complete_escalation(expected_version)
src/adlc/ledger/service.py          # expected_version on edit, upload and attach
src/adlc/config/settings.py         # deadletter_role, synthetic_dir and spec_dir to RuntimeSettings; UiSettings
deploy/compose.yaml                 # ui service; api gets the moved settings
tests/unit/inbox/  tests/unit/api/  tests/integration/api/  tests/integration/ui/
```

**Structure Decision**: `inbox/` is a read-side layer over features 003, 005 and 006. `api/` maps
HTTP to services. `ui/` is a pure client of the API.

## Complexity Tracking

No constitution violations; nothing to justify.
