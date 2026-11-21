# Implementation Plan: ADO Simulator Board

**Branch**: `017-ado-sim-board` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-ado-sim-board/spec.md` (Gate 1 approved
2026-11-21)

## Summary

Server-rendered pages inside the simulator's own FastAPI app, at the addresses ADO uses
(`/{org}/{project}/_boards/board`, `/{org}/{project}/_workitems/edit/{id}`): a sign-in page for the
seeded demo users (a personal page password, an optional shared demo password, or a personal access
token), the Epic board with one column per state, live refresh of the columns by HTMX polling, an
area filter, an Epic create form, and a read-only item page. Sessions are server-side rows (only a
hash of the cookie's id is stored), every form carries a CSRF token, every value is escaped. Board
settings (type, card fields, collapsed states, refresh) are seed data. The REST contract of 015 is
unchanged; no platform code changes.

## Technical Context

**Language/Version**: Python 3.12; the `ado_sim/` uv project (ruff, mypy strict, pytest, coverage
≥ 80%).

**Primary Dependencies**: FastAPI (as 015), Jinja2 3.1.6 and python-multipart 0.0.32 (new to the
simulator, already in the platform's lock; BSD-3-Clause and Apache-2.0), HTMX 2.0.4 vendored (0BSD).
Research, "Dependencies and licences".

**Storage**: the simulator's SQLite file; migration `0002_pages.sql` (`page_password`,
`page_session`); seed additions ([data-model.md](data-model.md)).

**Testing**:
- **Unit (test first)**: credential checks (each of the three, the service account refused, one
  message and comparable work for every failure); sessions (create, expire, revoke); CSRF; seed
  `board` validation; board grouping (process order, "other" column, collapsed states).
- **Pages** (FastAPI test client): a sweep of every page route without a session (redirect) and
  with one; every POST without CSRF (403); escaping of markup in titles, fields and descriptions;
  attribution of a page-created Epic (SC-003); the fragment's `HX-Redirect` on an expired session;
  security headers.
- **Accessibility**: a static checker over every page (research R-09, SC-005).
- **Properties**: 200 Epics, first view and refresh p95 (SC-001); 50 API changes visible on the next
  refresh (SC-002); no password, token or session id in any log line (SC-004).
- **Boundaries**: 015's boundary tests extended to templates and static files (no `adlc`, no
  `ADLC_`).

**Target Platform**: the demo host (compose service `ado-sim`, port 8600) and `make local`.

**Project Type**: pages added to an existing web service.

**Performance Goals**: first view ≤ 1 s and refresh ≤ 0.5 s at p95 with 200 Epics (SC-001).

**Constraints**: no external network for assets; no JavaScript beyond HTMX; the API contract and
its fixtures unchanged; values always escaped.

**Scale/Scope**: the demo: tens to 200 Epics, 15 demo users, one or two presenters.

## Constitution Check

*Gate before Phase 0; re-checked after Phase 1.*

| Article | How this plan complies |
| --- | --- |
| I, II Spec-driven, no values | board type, card fields and collapsed states are seed data; no terminal or field names in simulator code |
| III Agents build, humans decide | pages only change work items as their signed-in person; meaning stays with the platform (016) |
| IV Separation of duties | every page change is attributed to the signed-in user; the service account cannot sign in |
| V Evidence-first | page changes go through the same history as API changes |
| VII Interfaces | no change to the REST contract; boundary tests both ways cover templates and static files |
| VIII Open source, Python | Jinja2, python-multipart (already locked in the repository), vendored HTMX (0BSD) |
| IX Test first | credential, session, CSRF and seed modules test first |
| X Observable | page requests logged like API requests (operation, identity, status, duration) |
| XI Secure | hashed passwords and session ids, CSRF, escaping, CSP and security headers, one refusal message |
| XII Simplicity | server-rendered pages, polling, no front-end build, no signing library |

**Result: pass.** No deviation.

## Project Structure

### Documentation (this feature)

```text
specs/017-ado-sim-board/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/pages.md, contracts/cli-settings-seed.md
└── checklists/
```

### Source Code

```text
ado_sim/src/ado_sim/
├── migrations/0002_pages.sql
├── pages/
│   ├── __init__.py          routers for pages and static files
│   ├── sessions.py          create, read, revoke page sessions; CSRF
│   ├── signin.py            the three credentials; scrypt hashing
│   ├── board.py             board settings, columns and cards from the store
│   ├── routes.py            sign-in, board, fragment, create, item page
│   ├── templates/           base, signin, board, columns fragment, item, errors
│   └── static/              htmx.min.js (+ LICENSE), board.css
├── seed.py                  board settings and the service flag (validation)
├── settings.py              page session TTL, demo password, secure cookies
├── cli.py                   password set | clear
└── app.py                   page gate in the middleware; routers; headers
ado_sim/seed/demo.yaml       board section; service: true
ado_sim/tests/unit/          test_signin.py, test_sessions.py, test_board_settings.py, test_board.py
ado_sim/tests/pages/         test_access.py, test_board_pages.py, test_create.py, test_item.py, a11y.py
ado_sim/tests/properties/    test_board_timing.py, test_no_secrets_in_page_logs.py
```

**Structure Decision**: a `pages` package inside the simulator; the API modules are reused, not
changed, except the app's middleware (page gate) and the seed (board settings).

## Complexity Tracking

None.
