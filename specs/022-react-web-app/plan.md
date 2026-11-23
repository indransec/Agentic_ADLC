# Implementation Plan: Web Application Rebuild

**Branch**: `022-react-web-app` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/022-react-web-app/spec.md`

## Summary

Rebuild the Phase 1 web application (Streamlit, `src/adlc/ui`) as a browser application with
page-for-page parity, without the 019 console. This is the "React later" step that build plan §4
left open; it restores SA §17's original web stack, and it is recorded as ADR-05.

Four parts:

1. **Platform API** (small):
   - an HttpOnly, SameSite=Strict session cookie offered beside the bearer token;
   - a session-bound CSRF token for cookie requests (R-01, R-02);
   - strict Pydantic answer models for the 25 untyped routes, guarded by a golden-shape test
     (R-04);
   - the OpenAPI document exported and turned into TypeScript types, with freshness checked in
     Python and in the web build (R-05).
2. **The ui process** (`adlc.web`): stays Python. Starlette serves the built files with a strict
   CSP and proxies `/api/*` to the API unchanged, so there is no CORS and no new public path
   (R-03, R-11).
3. **The web application** (`web/`): React, TypeScript, Vite.
   - React Router keeps state in the address; TanStack Query handles reads and refreshes.
   - AG Grid Community is the artifact editor; the Plotly.js basic bundle draws the charts.
   - One page registry drives the navigation (R-06 to R-09).
4. **Tests and cutover:**
   - Vitest, Testing Library and typed MSW replace the `AppTest` suite row for row.
   - Playwright runs against a seeded, deterministic stack.
   - Streamlit runs on a temporary port until the parity checklist passes, then is removed
     (R-10, R-14).

## Technical Context

**Language/Version**:
- **Python 3.12** (uv, ruff, mypy strict, pytest) for the API changes and `adlc.web`.
- **TypeScript 5.x**, strict mode, for `web/`.
- **Node.js 24 LTS**, at build time only.

**Primary Dependencies**:
- **Python:** nothing new. Starlette, uvicorn and httpx are already dependencies.
- **Web**, all new (constitution VIII: every one OSI-licensed). Versions are pinned exactly in
  `web/package.json`, with `pnpm-lock.yaml` committed.

  | Package | Use | Licence |
  | --- | --- | --- |
  | `react`, `react-dom` | Views | MIT |
  | `typescript` | Language (strict) | Apache-2.0 |
  | `vite`, `@vitejs/plugin-react` | Dev server, build | MIT |
  | `react-router` | Client-side routes, address state | MIT |
  | `@tanstack/react-query` | Fetching, caching, interval refresh | MIT |
  | `ag-grid-community`, `ag-grid-react` | Artifact editor, tables (Community only, no Enterprise modules) | MIT |
  | `plotly.js-basic-dist-min` | Journey and portfolio charts | MIT |
  | `openapi-fetch` | Typed API client | MIT |
  | `openapi-typescript` | Types from the OpenAPI document (build) | MIT |
  | `vitest`, `@vitest/coverage-v8`, `jsdom` | Unit and component tests | MIT |
  | `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom` | Component tests | MIT |
  | `msw` | Typed API mocks | MIT |
  | `@playwright/test` | End-to-end tests | Apache-2.0 |
  | `@axe-core/playwright` | Accessibility checks (tests only, not shipped) | MPL-2.0 |
  | `eslint`, `typescript-eslint`, `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y`, `eslint-plugin-unicorn` | Lint | MIT |
  | `prettier` | Formatting | MIT |
  | pnpm (via corepack), Node.js 24 LTS | Package manager, build runtime (not at platform runtime) | MIT |

**Storage**: none new. No migration, and no data stored by the browser beyond the HttpOnly cookie.

**Testing**:
- **pytest:** cookie session, CSRF, golden answer shapes, OpenAPI freshness and the `adlc.web`
  server.
- **Vitest, Testing Library and MSW:** component tests (handlers typed by the generated schema).
- **Playwright (Chromium) and axe:** end-to-end tests against `tests/e2e/stack.py`, which seeds
  the harness with stub agents.
- CI runs `make check`, which now includes `web-check`.

**Target Platform**:
- **Server side:** Linux containers and macOS/Linux local runs, as today.
- **Browser side:** current desktop Chrome, Edge, Firefox and Safari (FR-029). End-to-end tests
  run Chromium; the others are checked manually at rehearsal.

**Project Type**: web application, with a Python API (existing), a Python ui process (new
package) and a browser application (new `web/` folder).

**Performance Goals**: every page shows content within 2 s on demo data, and editing and saving a
1,000-row table completes within 5 s (SC-007). The bundle splits code per page; Plotly and AG Grid
load only on the pages that use them.

**Constraints**:
- **Constitution I:** no terminal, control, role, outcome or threshold values in web code; the
  decision form is built from `run.form`.
- **Security:** the token never reaches JavaScript; `PUBLIC_PATHS` and API paths unchanged; no
  CORS; strict CSP.
- **Runtime:** no Node at runtime.

**Scale/Scope**:
- 12 pages, 25 API routes typed.
- About 4,500–6,000 lines of TypeScript and about 600 lines of Python.
- The roughly 660-line `AppTest` suite is replaced, along with roughly 1,900 lines of Streamlit
  code.

**Settings**:
- **New:** `ADLC_UI_DIST_DIR` (default `web/dist`), and `ADLC_LEGACY_UI_PORT` (default 8502,
  removed at cutover).
- **Reused:** `ADLC_API_URL`, `ADLC_UI_PORT`, `ADLC_UI_DASHBOARD_REFRESH`, `ADLC_ENV` and
  `ADLC_SESSION_SECRET` (CSRF HMAC key).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | The decision form, outcomes, root causes, terminals and roles come from API answers. Answer models type them as `str`, not literals. ESLint plus review keep terminal and role values out of `web/`. | Pass |
| II Superset, not values | No spec or profile change | Pass |
| III Humans decide | The application only relays people's decisions; the API enforces `status_rights` as today | Pass |
| IV Separation of duties | No agent or tool change | Pass |
| V Evidence-first | No ledger change; verification and evidence views read the API | Pass |
| VI Deterministic first | No judgement added | Pass |
| VII Interfaces | Only `src/api/client.ts` reaches the network (ESLint). `adlc.web` imports only `adlc.web` and `adlc.config` (boundary test). `IdentityProvider` is unchanged; the cookie is handled in `adlc.api.auth`. | Pass |
| VIII Open source, Python first | All new dependencies are OSI-licensed (R-06). The Python parts pass mypy strict and ruff. **Deviation:** the browser application is TypeScript, checked by `tsc --strict` and ESLint instead of mypy and ruff, and it needs Node at build time. | **Justified below** |
| IX Test first for core | No core area changes. The security-relevant session and CSRF tests (contracts/session.md) are still written and seen failing first. Core coverage is unaffected. | Pass |
| X Observable | No new run step, so no new `run_activity` row. The API keeps its spans; `adlc.web` logs method, path and status. | Pass |
| XI Secure by default | HttpOnly SameSite=Strict cookie, HMAC CSRF, login-CSRF header, no CORS, strict CSP, header allowlists in the proxy, no secrets or tokens in logs or bundle, `PUBLIC_PATHS` unchanged, deny by default kept | Pass |
| XII Simplicity for the MVP | **Deviation:** no new demo moment. The feature re-delivers D-1 to D-9 through the rebuilt application. Post-MVP items are listed in R-15 and not built. | **Justified below** |
| XIII Naming | Branch `022-react-web-app`; settings `ADLC_*`; cookie `adlc_session`; Python modules snake_case; every web file and folder name kebab-case (`run-page.tsx`, `decision-form.test.tsx`), per Annex A.1; component identifiers inside the code are PascalCase, which is code, not a file name; an ESLint `unicorn/filename-case` (MIT) rule enforces kebab-case | Pass |

**Demo moments supported** (constitution XII): D-1, D-2, D-3 (Run decision form), D-4
(Escalation), D-5 (Waiver), D-6 (Evidence and Verify), D-7 (Inbox proposed events and changes),
D-8 (Journey, Activity, Portfolio), D-9 (Clarification). None is new; each is re-delivered (see
quickstart §5).

**Post-design re-check**: Pass, with the two deviations justified in Complexity Tracking. No
constitution amendment is proposed. If the CoE lead and architect prefer, Article VIII can gain a
MINOR amendment: "browser code: TypeScript strict, OSI-licensed, Node at build time only".

## Project Structure

### Documentation (this feature)

```text
specs/022-react-web-app/
├── plan.md              # This file
├── research.md          # R-01 to R-15
├── data-model.md        # Session, CSRF value, page registry, runtime settings, contract, parity row
├── quickstart.md        # Validation guide
├── contracts/
│   ├── session.md            # Cookie session and CSRF (API)
│   ├── web-server.md         # adlc.web paths, headers, settings
│   ├── platform-contract.md  # Typed answers, OpenAPI export, freshness
│   ├── pages.md              # Pages, addresses, rendering and accessibility rules
│   └── parity.md             # The parity checklist (cutover condition)
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
src/adlc/api/
├── auth.py                    # + cookie session, CSRF check (contracts/session.md)
├── routes/auth.py             # + session mode, csrf_token, cookie set and clear
├── routes/*.py                # response_model on 25 routes
└── schemas/                   # NEW: base.py (ApiModel), runs.py, artifacts.py, inbox.py,
                               #      usecases.py, requests.py, changes.py, events.py, dashboard.py
src/adlc/web/                  # NEW: the ui process
├── __init__.py  __main__.py   # adlc-web console script (uvicorn)
├── server.py                  # Starlette app: proxy, static, config, health, headers
└── README.md
src/adlc/config/settings.py    # UiSettings + ui_dist_dir (+ legacy_ui_port until cutover)
src/adlc/ui/                   # Streamlit: unchanged until cutover, then removed
scripts/export_openapi.py      # NEW

web/                           # NEW: the browser application
├── package.json  pnpm-lock.yaml  tsconfig.json  vite.config.ts
├── eslint.config.js  .prettierrc  playwright.config.ts  index.html  README.md
├── src/
│   ├── main.tsx  app.tsx
│   ├── api/        client.ts  errors.ts  queries.ts  openapi.json  schema.d.ts
│   ├── auth/       session-context.tsx  sign-in-page.tsx  require-session.tsx
│   ├── nav/        registry.ts  sidebar.tsx  navigate.ts
│   ├── ui/         literal.tsx  status-badge.tsx  status.ts  format.ts  data-table.tsx
│   │               error-message.tsx  page-header.tsx  env-badge.tsx  theme.css
│   ├── pages/
│   │   ├── inbox/  intake/  use-cases/  journey/  activity/  portfolio/  dead-letters/
│   │   ├── requests/   clarification-page.tsx  escalation-page.tsx  waiver-page.tsx
│   │   └── run/        run-page.tsx  summary-bar.tsx  artifact-panel.tsx  artifact-grid.tsx
│   │                   review-panel.tsx  control-results.tsx  decision-form.tsx  detail-tabs.tsx
│   └── test/       msw-handlers.ts  fixtures/  setup.ts
└── e2e/            session  intake  sign-off  artifacts  stale  requests  rendering
                    navigation  a11y  timing  (.spec.ts)

tests/
├── integration/api/   test_cookie_session.py  test_csrf.py  test_response_shapes.py  (NEW)
├── integration/web/   test_server.py  (NEW)
├── unit/api/          test_openapi_fresh.py  (NEW)
├── unit/test_ui_boundary.py   # retargeted to src/adlc/web at cutover (covers both until then)
├── e2e/stack.py       # NEW: seeded API + adlc-web for Playwright
└── integration/ui/    # AppTest suite: removed at cutover

Makefile                       # + web-build, web-dev, web-lint, web-typecheck, web-test, web-e2e,
                               #   web-check, openapi; install and local-setup extended; check + web-check
.github/workflows/ci.yml       # + setup-node, corepack, Playwright Chromium
deploy/api.Dockerfile          # + node build stage; copy web/dist; drop .streamlit at cutover
deploy/compose.yaml            # ui: adlc-web, /health; legacy-ui service until cutover
deploy/Procfile.local          # ui: uv run adlc-web; legacy-ui until cutover
.env.example, deploy/local.env # + ADLC_UI_DIST_DIR (+ ADLC_LEGACY_UI_PORT until cutover)
docs/                          # SA §8 and §17 (ADR-05), build plan §4, run-without-docker, user manual
```

**Structure Decision**: the API stays where it is, with a new `schemas/` package. The ui process
becomes a new Python package, `adlc.web`, so Streamlit can run beside it unchanged until cutover.
The browser application lives in a top-level `web/` folder with its own toolchain, outside
`src/adlc`, which stays one typed Python package (constitution, "Repository and Spec
Boundaries").

## Delivery slices (order for /speckit-tasks)

1. **API session:** the cookie session and CSRF, test first (US1).
2. **API contract:**
   - the golden-shape test first;
   - then the answer models;
   - then `export_openapi` and the freshness test (FR-020, FR-021).
3. **Scaffold and serving:**
   - `adlc.web`, its tests and settings;
   - `web/` with lint rules, the client, the session context, the registry and shell, and
     sign-in;
   - Makefile targets, CI, the Procfile and compose (legacy UI on 8502);
   - the e2e stack and `session.spec.ts`.
4. **Read-only pages** (US5, US6): Use cases (with verify), Journey, Activity, Portfolio, Dead
   letters.
5. **Requests** (US4): Intake, Inbox (with change and proposed-event decisions), Clarification,
   Escalation, Waiver.
6. **Run page** (US2, US3):
   - summary bar, review, controls, decision form, detail tabs;
   - artifact grid, upload, attachments, history;
   - stale handling.
7. **Parity and hardening:**
   - the remaining e2e specs, axe, timing and CSP checks;
   - every parity row passing;
   - a manual browser check (Edge, Firefox, Safari).
8. **Cutover and docs:**
   - remove Streamlit (R-14);
   - ADR-05 in SA §17 and build plan §4;
   - SA §8; the `adlc.web` and `web/` READMEs; `docs/run-without-docker.md`;
     `docs/user-manual.md`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --- | --- | --- |
| VIII: browser code in TypeScript, Node at build time | The feature's purpose is a browser application, which SA §17 chose originally (React); build plan §4 kept that path open. Browser code cannot be Python without a Python-in-browser runtime. TypeScript strict, `tsc` and ESLint give the same guarantees mypy and ruff give the Python code. Node is confined to building: the runtime stays all-Python (`adlc.web` serves static files), which preserves the branch's all-Python infrastructure goal. | Keeping Streamlit does not meet the request. Python-to-browser frameworks (Reflex, NiceGUI, Pyodide) either still ship a JavaScript build or render on the server like Streamlit, and they lack a 1,000-row editable grid with keyboard and accessibility support. Committing a prebuilt `web/dist` to skip Node in CI hides drift and makes reviews of generated files noisy. |
| XII: no new demo moment | It re-delivers D-1 to D-9 through the application they are shown in, with a better grid, in-place updates and a typed contract. The scope is held to parity, and everything else is listed post-MVP (R-15). | Deferring until after the demo is the alternative. It is acceptable to the constitution but was not the user's choice. The slices are ordered so the branch stays demo-ready throughout: Streamlit keeps working until cutover. |
