# Tasks: Web Application Rebuild

**Input**: Design documents from `specs/022-react-web-app/` (spec, plan, research, data-model,
contracts, quickstart)

**Tests**: requested by the spec (FR-025, parity checklist). Session and CSRF tests and the golden
answer-shape test are written first and seen failing (constitution IX, contracts/session.md,
contracts/platform-contract.md). CI runs `make check`; run the relevant suites locally while
working: `uv run pytest <paths>`, `pnpm -C web test`, `pnpm -C web exec playwright test <spec>`.

**Format**: `[ID] [P?] [Story] Description`. `[P]` means a different file with no dependency on
an unfinished task. Parity ids (P-nn, N-nn) refer to `contracts/parity.md`. Mark a parity row
`passing` there when its tests pass.

**Rules for every task**:
- No terminal, control, role, outcome or threshold value in `web/` or `adlc.web`
  (constitution I).
- Agent and person text goes only through `<Literal>` or grid text cells (contracts/pages.md,
  "Rendering rules").
- Every run action sends `expected_version` (research R-08).

---

## Phase 1: Setup

- [X] T001 Settings in `src/adlc/config/settings.py` `UiSettings`:
  - `ui_dist_dir: Path`, default `web/dist` (`ADLC_UI_DIST_DIR`);
  - `legacy_ui_port: int`, default `8502` (`ADLC_LEGACY_UI_PORT`), with the comment "removed at
    the 022 cutover".

  Add both to `.env.example` and `deploy/local.env`, and update `tests/unit/test_env_example.py`
  if it lists variables.
- [X] T002 Scaffold `web/`:
  - `package.json`: `"packageManager": "pnpm@<pinned>"`, `"engines": {"node": ">=24 <25"}`, and
    exact versions of every package in research R-06.
  - Scripts: `dev`, `build`, `lint`, `format:check`, `typecheck`, `test`, `e2e`, `openapi`.
  - `pnpm-lock.yaml`, `tsconfig.json` (strict, `noUncheckedIndexedAccess`,
    `exactOptionalPropertyTypes`), `index.html`.
  - `vite.config.ts`: dev proxy of `/api` and `/config.json` to
    `http://127.0.0.1:${ADLC_UI_PORT}`; one chunk per page; Plotly and AG Grid in their own
    chunks.
  - `src/main.tsx` rendering an empty `App`.
  - `.nvmrc` with `24`.
- [X] T003 [P] `web/eslint.config.js` and `web/.prettierrc`: typescript-eslint strict,
  react-hooks, jsx-a11y recommended, and these errors (research R-11):
  - `react/no-danger`;
  - `no-restricted-properties` for `innerHTML` and `outerHTML`;
  - `no-restricted-globals` for `fetch` and `XMLHttpRequest`, with an override allowing them in
    `src/api/client.ts` only;
  - `no-restricted-imports` for `openapi-fetch` outside `src/api/**`;
  - `unicorn/filename-case` with `kebab-case` for every file in `web/` (constitution XIII, Annex
    A.1). Component identifiers stay PascalCase in code.

  Add `web/src/lint-guard.test.ts`, which runs ESLint on fixture snippets
  (`web/src/test/lint-fixtures/`) and asserts each banned pattern, including a PascalCase file
  name, is reported (P-27).
- [X] T004 [P] Vitest and MSW setup: `web/vitest.config.ts` (jsdom, coverage),
  `web/src/test/setup.ts` (jest-dom, MSW server lifecycle, `onUnhandledRequest: "error"`), and
  `web/src/test/render.tsx` (renders with router, query client and session providers).
- [X] T005 [P] `.gitignore`: `web/node_modules/`, `web/dist/`, `web/coverage/`,
  `web/test-results/`, `web/playwright-report/`.
- [X] T006 Makefile targets:
  - `web-install` (`corepack enable && pnpm -C web install --frozen-lockfile`);
  - `web-build`, `web-dev`, `web-lint` (eslint and prettier check);
  - `web-typecheck` (`tsc --noEmit`, then regenerate `schema.d.ts` into a temp file and `diff`
    it with the committed one);
  - `web-test` (vitest run with coverage), `web-e2e` (depends on `web-build`, then playwright
    test, so it always runs against a fresh `web/dist`);
  - `web-check` (the four checks), `openapi` (contracts/platform-contract.md "Generation").

  Also: `install` calls `web-install`, `local-setup` calls `web-build`, `check` calls
  `web-check`, and `.PHONY` and `help` are updated.
- [X] T007 `.github/workflows/ci.yml`: `actions/setup-node@v4` (node-version-file
  `web/.nvmrc`, pnpm cache on `web/pnpm-lock.yaml`), `corepack enable`, then
  `pnpm -C web exec playwright install --with-deps chromium`, all before `make install` and
  `make check`.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T008 [P] `tests/integration/api/test_response_shapes.py` (N-08). On the orchestration
  harness's scripted walk, use the patterns in `tests/integration/test_auth_api.py` and
  `tests/support/api.py`. The walk must cover:
  - use case submitted;
  - a run awaiting sign-off with artifacts, controls, a recommendation and an attachment;
  - a clarification, an escalation, a waiver, a change request, a proposed event and a dead
    letter;
  - a journey with a rework.

  Call each of the 25 routes in contracts/platform-contract.md and compare the JSON with golden
  files in `tests/integration/api/golden/<route-id>.json`. Normalise ids, times and hashes
  through a helper, and record the goldens with `--update-golden` **before** any model exists.
  Add the `--update-golden` option in `tests/integration/api/conftest.py` (`pytest_addoption`;
  off by default, so CI only compares). Commit the goldens in this task.
- [X] T009 [P] `tests/unit/api/test_openapi_fresh.py`: builds the app with test settings,
  compares `app.openapi()` (sorted keys, 2-space indent) with `web/src/api/openapi.json`, and
  fails with "run `make openapi`" (N-09). It fails until T013.
- [X] T010 [P] `tests/integration/web/test_server.py`, covering every case in the "Tests" list of
  contracts/web-server.md (proxy, header allowlists, streaming upload, 502 shape, SPA fallback,
  asset caching and 404, traversal refused, `/config.json`, `/health` with a missing build, the
  CSP and other headers on every answer, no CORS headers). Use a stub API Starlette app over
  `httpx.MockTransport`, and a temporary dist folder.

### Platform contract (contracts/platform-contract.md)

- [X] T011 `src/adlc/api/schemas/__init__.py` and `src/adlc/api/schemas/base.py`:
  `class ApiModel(BaseModel)` with `model_config = ConfigDict(extra="forbid")`, plus `JsonValue`
  re-exported from pydantic. Write a unit test showing an undeclared key raises
  (`tests/unit/api/test_api_model.py`).
- [X] T012 [P] Answer models, one module per router, field names exactly as today's keys:
  - `src/adlc/api/schemas/runs.py`: run detail including `run`, `timer`, `spec`, `cost`,
    `artifacts`, `form`, `prerequisites`, `prior_rework`, `clarifications`, `approvals`,
    `waiver`, `activity`, `evidence`; decision and escalation answers.
  - `src/adlc/api/schemas/artifacts.py`: save, spreadsheet, attachment, history.
  - `src/adlc/api/schemas/inbox.py`.
  - `src/adlc/api/schemas/usecases.py`: create, list, detail, verify.
  - `src/adlc/api/schemas/requests.py`: clarification answer, waiver decision, dead-letter list
    and detail.
  - `src/adlc/api/schemas/changes.py`, `src/adlc/api/schemas/events.py`.
  - `src/adlc/api/schemas/dashboard.py`: journey, KPIs, portfolio, activity, timeline.

  Spec- and catalogue-driven values are `str`, not `Literal`; open content (artifact rows and
  cells, payloads, control details) is `JsonValue`. Shapes start from
  `specs/007-human-inbox/contracts/api.md` and
  `specs/013-lifecycle-dashboard/contracts/api-dashboard.md`, checked against the services.
- [X] T013 Set `response_model=` on the 25 routes in `src/adlc/api/routes/{artifacts,changes,
  dashboard,events,inbox,requests,runs,usecases}.py`. Add `responses=` documentation for the
  three raw routes:
  - attachment download: `application/octet-stream` with `Content-Disposition`;
  - sign-out: 204;
  - re-queue: 204.

  T008 must pass unchanged.
- [X] T014 `scripts/export_openapi.py` (`python -m scripts.export_openapi`): builds the app with
  dummy settings, no database access. Run `make openapi` to commit `web/src/api/openapi.json` and
  `web/src/api/schema.d.ts`. T009 then passes.

### The ui process (contracts/web-server.md)

- [X] T015 `src/adlc/web/__init__.py`, `src/adlc/web/server.py`, `src/adlc/web/__main__.py`.
  - `server.py` holds `create_app(settings: UiSettings, transport: httpx.AsyncBaseTransport |
    None = None) -> Starlette`. It implements every path and header in contracts/web-server.md:
    the streamed proxy via `httpx.AsyncClient`, both allowlists, 502 `unavailable`,
    `/config.json`, `/health`, `/assets` caching, the SPA fallback, traversal guard, the security
    headers on every answer, and logging of method, path and status only.
  - `__main__.py` runs uvicorn with `--host`, default `127.0.0.1`, and `ADLC_UI_PORT`.
  - Add the console script `adlc-web = "adlc.web.__main__:main"` in `pyproject.toml`.

  T010 passes.
- [X] T016 [P] `tests/unit/test_ui_boundary.py`: scan `src/adlc/web/` as well, allowing only
  `adlc.web` and `adlc.config`. Add `"adlc.web"` to the forbidden lists in
  `tests/unit/test_knowledge_boundary.py` and `tests/unit/tools/test_boundary.py` (P-27).
- [X] T017 [P] `src/adlc/web/README.md`: paths, settings, headers, boundary, how to build and run.

### Web foundations

- [X] T018 `web/src/api/client.ts`:
  - `openapi-fetch` client with `baseUrl: "/api"` and `credentials: "same-origin"`.
  - Middleware adds `X-ADLC-CSRF` from the session store on non-GET, HEAD or OPTIONS requests.
  - Answers map to `ApiError {status, kind, detail, field?}`. A network failure becomes
    `unavailable`.
  - A helper `downloadAttachment(runId, hash, name)` fetches a blob, re-wraps it as
    `application/octet-stream` and clicks an `<a download>` (research R-11).
  - FR-009 holds by construction: the client calls only paths typed in `openapi.json`, and this
    branch has no `/board` routes. Add no board path to it.

  Add `web/src/api/errors.ts`, which maps each kind to behaviour per the data-model table, and
  `web/src/api/client.test.ts` (each kind, the CSRF header present and absent, unavailable
  keeping input: N-06).
- [X] T019 [P] `web/src/api/queries.ts`: typed query keys and hooks per route (TanStack Query),
  and mutation helpers that invalidate the run, inbox and use-case keys (research R-07).
  `refetchIntervalInBackground: false`.
- [X] T020 [P] `web/src/ui/literal.tsx` (`white-space: pre-wrap; overflow-wrap: anywhere`, text
  node only) and `web/src/ui/literal.test.tsx`. The test feeds markup and script samples (copy
  the samples from `tests/integration/ui/test_rendering.py`) and asserts each renders as literal
  text with no element created (P-13).
- [X] T021 [P] `web/src/ui/status.ts`: port `STATUS` and `STATUS_COLOURS` from
  `src/adlc/ui/render.py`. Then `web/src/ui/status-badge.tsx` and `status-badge.test.tsx`: a known
  value shows the word and colour; an unknown one is plain text; the badge is never colour-only.
- [X] T022 [P] `web/src/ui/format.ts`: port `src/adlc/ui/format.py` (UTC times, durations,
  money, column names), with `format.test.ts` mirroring its behaviour.
- [X] T023 [P] `web/src/ui/data-table.tsx`: an AG Grid Community read-only wrapper with text cell
  renderer only, column labels via `format.ts`, and an empty-state text. Also
  `error-message.tsx` ("The platform refused this: <kind in words>", detail through `<Literal>`),
  `page-header.tsx` (focus on mount, FR-028), `env-badge.tsx` and `theme.css`, which ports the
  colours and fonts from `.streamlit/config.toml`.
- [X] T024 `web/src/config.ts`: load `/config.json` once (`env`, `dashboard_refresh_seconds`)
  and provide it through context.
- [X] T025 `web/src/nav/registry.ts`: every page in contracts/pages.md, in that order, with
  fields `id`, `title`, `section`, `path`, `icon`, `inSidebar`, `params` and `component` (data-model
  "Page registry entry"). Pages not built yet use a lazy placeholder component.

  Also:
  - `web/src/nav/sidebar.tsx`: sections in registry order, environment badge, person and roles,
    sign-out slot.
  - `web/src/nav/navigate.ts`: `navigate(id, params)` builds the address from the registry.
  - `web/src/app.tsx`: router built from the registry, unknown path → "page not found", `/` →
    `/run?run=` when `run` is present, otherwise `/inbox`.
  - `web/src/nav/registry.test.ts`: the sidebar shows exactly the `inSidebar` pages; every path
    is unique; `/?run=X` redirects (FR-002, FR-003).
- [X] T026 [P] `web/src/test/msw-handlers.ts` and `web/src/test/fixtures/*.json`: handlers typed
  with `paths` from `schema.d.ts`, with fixtures taken from the T008 goldens. The type check fails
  if a fixture or handler stops matching the contract.
- [X] T027 `tests/e2e/stack.py`: a Python entry point (`uv run python -m tests.e2e.stack`). It
  builds a fresh harness database with stub agents (`tests/support/orchestration.py`), writes an
  accounts file with test roles, and seeds:
  - a run awaiting sign-off;
  - a run whose artifact has 1,000 rows and one with 1,001;
  - a clarification, an escalation, a waiver, a change request, a proposed event, a dead letter
    and a blocked run.

  It starts the API (uvicorn) and `adlc-web` (dist from `web/dist`) on free ports, runs a drain
  loop thread, prints the base URL and the seeded ids as JSON, and writes a ready file.
  Add `web/playwright.config.ts` (Chromium; a `globalSetup` that starts the stack and reads the
  JSON; base URL from it) and `web/e2e/fixtures.ts` (sign-in helper, seeded ids,
  console-error/CSP-violation listener that fails the test).
- [X] T028 Running both ways (research R-13, R-14):
  - `deploy/Procfile.local`: `ui: uv run adlc-web --host 127.0.0.1`; the old Streamlit line
    renamed to `legacy-ui`, on `${ADLC_LEGACY_UI_PORT:-8502}`.
  - `deploy/api.Dockerfile`: add a first stage, `FROM node:24-slim AS web` (`corepack enable`,
    copy `web/`, `pnpm install --frozen-lockfile`, `pnpm build`), then
    `COPY --from=web /web/dist ./web/dist` in the Python stage.
  - `deploy/compose.yaml`: the `ui` service runs `adlc-web --host 0.0.0.0`, with the health check
    on `http://127.0.0.1:8501/health` and `ADLC_UI_DIST_DIR: /app/web/dist`; a temporary
    `legacy-ui` service runs Streamlit on 8502.
  - `deploy/README.md`.

**Checkpoint**:
- `make check` passes;
- `make local` serves the empty shell on 8501, with Streamlit on 8502;
- the T008 goldens are unchanged.

---

## Phase 3: User Story 1 – Sign in, and the session stays out of reach (P1) 🎯 MVP

**Goal**: cookie-mode sign-in and a session-bound CSRF token in the API; sign-in, sign-out,
expiry and deep links in the web application.

**Independent Test**:
- sign in; the cookie is HttpOnly and `document.cookie` and storage hold no token;
- sign out;
- open `/?run=<id>` signed out and land on the run after signing in;
- a cross-site POST is refused.

### Tests first (seen failing)

- [X] T029 [P] [US1] `tests/integration/api/test_cookie_session.py`: every sign-in, read,
  sign-out and public-path case in contracts/session.md "Tests". This includes `Secure` when
  `X-Forwarded-Proto: https`, and the token never appearing in a cookie-mode body.
- [X] T030 [P] [US1] `tests/integration/api/test_csrf.py` (N-02). A cookie POST is refused with
  403 `not_allowed` "cross-site request refused" when the header is missing, wrong, or from
  another session. A bearer POST without the header passes. Cookie-mode sign-in without
  `X-ADLC-CSRF: sign-in` is refused. Sign-out with the cookie needs the header.

### Implementation

- [X] T031 [US1] `src/adlc/api/auth.py`:
  - `session_cookie(request)`, and a `csrf_value(secret, token)` function computing
    `base64url(HMAC-SHA256(session_secret, "csrf\0" + token))`, compared with
    `hmac.compare_digest`.
  - The middleware tries bearer first, then the cookie `adlc_session`. For cookie requests whose
    method is not GET, HEAD or OPTIONS, it requires `X-ADLC-CSRF`.
  - It sets `request.state.session_via = "bearer" | "cookie"`.
  - `install_auth` takes the session secret from `app.state.settings`.
  - `PUBLIC_PATHS` is unchanged.
- [X] T032 [US1] `src/adlc/api/routes/auth.py`:
  - `SignInRequest.session: Literal["bearer", "cookie"] = "bearer"`.
  - In cookie mode, require the header `X-ADLC-CSRF: sign-in` (403 otherwise). Answer
    `BrowserSignInResponse {expires_at, person, csrf_token}` and set the cookie
    `adlc_session=<token>; HttpOnly; SameSite=Strict; Path=/; Max-Age=<n>`, plus `Secure` when
    the scheme or `X-Forwarded-Proto` is https.
  - `/auth/me` adds `csrf_token` only when `session_via == "cookie"`.
  - Sign-out clears the cookie when `session_via == "cookie"`.

  Bearer answers stay byte-identical. Then run `make openapi`. T029 and T030 pass, and the
  existing `tests/integration/test_auth_api.py` passes unchanged.
- [X] T033 [US1] `web/src/auth/session-context.tsx`:
  - holds the person and the CSRF value in memory only;
  - at start calls `GET /auth/me` (401 means signed out);
  - offers `signIn(account, password)` (cookie mode with the `sign-in` header) and `signOut()`;
  - on any `not_signed_in` from the client, clears its state and navigates to
    `/sign-in?next=<current path and query>`.
- [X] T034 [US1] `web/src/auth/sign-in-page.tsx`: logo, tagline and environment badge; Account and
  Password fields with visible labels; "Sign in". A wrong password shows the platform's message.
  After sign-in, follow `next` only if it starts with exactly one `/`; otherwise go to `/inbox`.

  Also `web/src/auth/require-session.tsx`, which wraps every registry page, and the sign-out
  button in `sidebar.tsx`. Add `web/src/auth/sign-in-page.test.tsx` and
  `require-session.test.tsx`: wrong password; `next` honoured; `//evil.example` and
  `https://evil.example` ignored; expiry during an action goes to sign-in without resending.
- [X] T035 [US1] `web/e2e/session.spec.ts` (P-02, N-01, N-02, N-03):
  - sign in, then assert `document.cookie` lacks `adlc_session` and local and session storage
    hold no token, while the context's cookies show HttpOnly and SameSite Strict;
  - sign out and get sent back to sign-in;
  - an expired session (stack helper revokes it) gives sign-in with `next`;
  - signed out, `/?run=<seeded id>` leads to sign-in and then the Run page;
  - cross-site: fulfil a fake page at `http://127.0.0.1:<free port>/attack.html` with Playwright
    `page.route` (no server). The page auto-submits a form POST to
    `<app>/api/usecases`. The answer must be 403 with `"kind": "not_allowed"` (asserted on the
    response, so a 422 cannot pass the test), and `GET /api/usecases` shows no new use case.

### Implementation notes (2026-11-23)

- **T001:** `ADLC_UI_PORT` became a `UiSettings` field, because `adlc-web` reads it.
  `ADLC_LEGACY_UI_PORT` stayed deploy-only (compose and the Procfile), like `ADLC_PHOENIX_UI_PORT`,
  because no Python reads it.
- **T007:** CI runs only make targets (`tests/unit/test_build_contract.py`). The Playwright browser
  install is therefore `make web-browsers`, a setup-only run beside `make install`.
- **T012/T013:** strict models for every dict built in code. Rows passed through from the store
  (sign-offs, clarifications, waiver, reviewer output, checks, timeline) are `Record`
  (`dict[str, Any]`), because their values include datetimes and decimals and their keys follow
  the store. Routes use `response_model_exclude_unset`, so keys that are sometimes absent stay
  absent. All 25 goldens, the API, dashboard, Streamlit UI and scenario suites pass unchanged.
- **T015:** the proxy's httpx client uses a cookie jar that stores nothing. The first e2e run
  showed the default jar carrying one person's session to every later request; a regression test
  in `test_server.py` covers it.
- **T019:** query keys and the client defaults are in place; per-route hooks arrive with each page
  (US2 to US6).
- **T023:** read-only tables are a semantic `<table>` (accessible, testable in jsdom). AG Grid is
  kept for the artifact editor and large tables (US3).
- **T033:** the session records a deliberate sign-out, so sign-in then opens without a `next`
  address.

**Checkpoint**: US1's independent test passes; parity rows P-02, N-01, N-02 and N-03 are
`passing`.

---

## Phase 4: User Story 2 – An approver decides on a run with full context (P1)

**Goal**: the Run page, except artifact editing: summary, review, controls, decision form,
detail tabs and stale handling.

**Independent Test**: on seeded runs, pass one and send another to rework with a comment and root
cause; a concurrent change gives the stale message; a blocked run explains itself and can be
terminated.

### Tests

- [X] T036 [P] [US2] `web/src/pages/run/decision-form.test.tsx` (P-05, P-06), driven only by a
  `form` fixture:
  - the outcomes offered are exactly `form.outcomes`, or only `terminate` when only
    `can_terminate`;
  - comment for rework and terminate; root cause from `root_causes`; owning terminal only when
    the cause is in `target_terminal_for`;
  - `requires[decision]` fields and, on pass, `typed_fields` and alternatives;
  - the reason is asked when the choice differs from `reason_required_unless` (and is not
    terminate);
  - the controls-pending and waiver-pending notices; "You have no decision to make on this run";
  - the stale answer gives a reload and the message "This run changed since you opened it. It
    has been reloaded; check it and act again.", with nothing recorded.
- [X] T037 [P] [US2] `web/src/pages/run/run-page.test.tsx` (P-07, P-14, P-19 evidence tab):
  - summary bar fields (run, version, terminal and spec version, state and final status, due
    with overdue badge, model cost, "Controls are being re-run");
  - the blocked notice "Blocked by an unmet prerequisite (see Prerequisites). Supply the
    evidence, or terminate the run below.";
  - nine tabs, each with a count when it has content;
  - findings, comments, reasons and file names carrying markup samples render as literal text;
  - an unknown run gives "not found" with a link back.

### Implementation

- [X] T038 [P] [US2] `web/src/pages/run/summary-bar.tsx` and `web/src/pages/run/review-panel.tsx`
  (the reviewer recommendation and findings via `<Literal>`).
- [X] T039 [P] [US2] `web/src/pages/run/control-results.tsx`: counts of passed and blocking-failed
  controls, as platform words, plus the results table via `DataTable` with "No controls have run
  yet.".
- [X] T040 [P] [US2] `web/src/pages/run/detail-tabs.tsx`: Prerequisites, Citations (from each
  artifact's `citations`), Prior rework, Clarifications, Approvals, Waiver, Activity, Timeline
  (`GET /dashboard/runs/{id}/timeline`) and Evidence, each a `DataTable` or `<Literal>` block.
- [X] T041 [US2] `web/src/pages/run/decision-form.tsx`: per T036, built only from `run.form`. It
  submits `{decision, expected_version: seen, fields, comment?, root_cause?, target_terminal?,
  reason?}` to `POST /runs/{id}/decisions` and shows "Decision recorded".
- [X] T042 [US2] `web/src/pages/run/run-page.tsx`: reads `?run=` from the address and loads
  `GET /runs/{id}`. It keeps the *seen* version in a ref updated after each render, not on
  background refetch (research R-08). On `stale` it refetches, sets the seen version and shows the
  message. Layout: summary bar; artifacts (slot for US3) beside the review, controls and decision
  form; then the tabs. Register it in `registry.ts`. T036 and T037 pass.
- [X] T043 [US2] `web/e2e/sign-off.spec.ts`: open a seeded run by link, pass it, see "Decision
  recorded" and the new state; rework with comment and root cause. Then `web/e2e/stale.spec.ts`:
  open a run, change it through the stack's API helper, decide, and get the stale message with
  nothing recorded (P-06).

### Implementation notes (2026-11-23, US2)

- **"Decision recorded" lives on the page, not in the form.** The form remounts when the run's
  version changes, which it does right after a decision, so the page keeps the notice.
- **The run is not refreshed in the background.** The version shown is therefore always the
  version the person acts on (research R-08). Only the person's own decision or a stale answer
  reloads it.
- **Artifacts are read-only here** (`artifacts-read-only.tsx`); US3 replaces this with the
  editing panel.
- **Parity, kept:** the rework `requires` list includes `owner_comment`, which the platform
  satisfies from the decision's comment. Like the Streamlit form, the form shows it as its own
  input.

**Checkpoint**: an approver can decide any seeded run from a link; parity rows P-05, P-06, P-07
and P-14 are `passing`.

---

## Phase 5: User Story 3 – Approvers edit artifacts before approving (P1)

**Goal**: the artifact panel on the Run page: an editable grid up to 1,000 rows, read-only above
that with upload, history, and download-only attachments.

**Independent Test**: edit and save a 1,000-row artifact; a 1,001-row artifact is read-only with
upload offered; upload a spreadsheet; attach a file and download it.

### Tests

- [X] T044 [P] [US3] `web/src/pages/run/artifact-panel.test.tsx` (P-09, P-10, P-11):
  - edit a cell and Save sends `{rows, expected_version}` to `PUT /runs/{id}/artifacts/{aid}` and
    shows "Saved";
  - add and remove rows;
  - non-editors get a read-only grid with no upload;
  - 1,000 rows are editable, while 1,001 are read-only with the caption "More than 1000 rows:
    upload a spreadsheet to change it.";
  - "Not built yet" with no version;
  - the History toggle loads `/history`;
  - cells with markup samples render literally;
  - stale on save gives the stale message.

### Implementation

- [X] T045 [US3] `web/src/pages/run/artifact-grid.tsx`: AG Grid Community.
  - When editable and `rows.length <= 1000`: editable text cells, add and remove row controls
    with visible labels, keyboard navigation.
  - Otherwise: read-only.
  - Columns come from `artifact.columns`, or else the row keys.
  - The default text renderer only; no HTML cell renderers. Export the constant
    `MAX_EDIT_ROWS = 1000`, the platform-wide editor limit from 007, not a terminal value.
- [X] T046 [US3] `web/src/pages/run/artifact-panel.tsx`:
  - artifact id and version, or "Not built yet"; the grid; "Save <id>";
  - attachments listed with the file name via `<Literal>` and a "Download" button using
    `downloadAttachment` (never inline);
  - "Upload a spreadsheet or attach a file": an `.xlsx` upload to `…/spreadsheet` and a file
    attach to `…/attachments`, both multipart with `expected_version`;
  - a History toggle.

  Plug it into the `run-page.tsx` slot. T044 passes.
- [X] T047 [US3] `web/e2e/artifacts.spec.ts` (P-09, P-11, P-12): edit and save the seeded
  1,000-row artifact within 5 s (SC-007); the 1,001-row artifact is read-only with upload; upload
  a spreadsheet fixture (`web/e2e/fixtures/artifact.xlsx`); attach an HTML file and click
  Download, which gives a download event and no new page or frame rendering it.

### Implementation notes (2026-11-23, US3)

- **Grid stand-in for component tests.** The panel's component tests replace the grid with a
  stand-in, as the Streamlit tests replaced `st.data_editor`: AG Grid needs a real browser to lay
  out. `e2e/artifacts.spec.ts` drives the real grid (edit and save 1,000 rows in under 5 s,
  1,001 read-only, spreadsheet upload, SVG attachment downloaded and never rendered).
- **Uploads checked at the typed client.** In jsdom, Node's fetch cannot send jsdom's
  `FormData`, so the upload component tests check the form the panel builds; the browser test
  sends it for real.
- **Lazy loading.** The Run page loads on first use, so AG Grid (about 346 KB gzipped) is not
  in the shell's bundle.

**Checkpoint**: parity rows P-09 to P-12 are `passing`.

---

## Phase 6: User Story 4 – Requests reach the right person and are answered (P2)

**Goal**: New use case, Inbox (with change requests and proposed events), Clarification,
Escalation and Waiver.

**Independent Test**: submit a use case; answer a clarification; complete an escalation; decide a
waiver; decide a change request and a proposed event. Each item leaves the Inbox.

### Tests

- [X] T048 [P] [US4] `web/src/pages/intake/intake-page.test.tsx` (P-01, P-03): Name and
  Description; submit goes to Use cases with "Submitted"; a 422 with `field` is shown beside that
  field.
- [X] T049 [P] [US4] `web/src/pages/inbox/inbox-page.test.tsx` (P-04, P-08, P-20, P-21, N-05):
  - "Decisions and requests waiting for you, oldest first.", grouped by kind as today;
  - a controls-being-rerun mark;
  - Open goes to the page for the kind (run, clarification, waiver, escalation, dead letters);
  - change requests with "Record decision" (approve or reject, comment), only for those who have
    any;
  - proposed events with a decision;
  - refresh every 30 s (fake timers) and on demand, without clearing a half-typed comment.
- [X] T050 [P] [US4] `web/src/pages/requests/clarification-page.test.tsx`,
  `escalation-page.test.tsx` and `waiver-page.test.tsx` (P-15, P-16, P-17):
  - one answer field per question;
  - the escalation notice "You cannot complete this run." when not allowed;
  - the waiver decision with comment;
  - questions, reasons and comments rendered literally.

### Implementation

- [X] T051 [P] [US4] `web/src/pages/intake/intake-page.tsx`: `POST /usecases`, then
  `navigate("use-cases", {usecase})` with a submitted notice.
- [X] T052 [P] [US4] `web/src/pages/inbox/inbox-page.tsx`: `GET /inbox` with `refetchInterval:
  30_000` and a Refresh button. Item selection labels use platform words (kind, id, time); the
  person-written text sits beside them in `<Literal>`. Change requests come from `GET /changes`,
  with a decision via `POST /changes/{id}/decision`. Proposed events come from
  `GET /events/proposed`, with a decision via
  `POST /events/proposed/{usecase}/{terminal}/{run}/{event}`.
- [X] T053 [P] [US4] `web/src/pages/requests/clarification-page.tsx`,
  `web/src/pages/requests/escalation-page.tsx` and `web/src/pages/requests/waiver-page.tsx`: port
  `src/adlc/ui/views/{clarification,escalation,waiver}.py`; ids from the address (`?run=&id=`);
  actions send `expected_version` where the API takes it.
- [X] T054 [US4] Register the five pages in `web/src/nav/registry.ts`. T048 to T050 pass.
- [X] T055 [US4] `web/e2e/intake.spec.ts` (P-01): submit a use case and follow it to Use cases.
  Then `web/e2e/requests.spec.ts` (P-15 to P-17): answer the seeded clarification, complete the
  escalation, decide the waiver; each leaves the Inbox. Extend `sign-off.spec.ts` with
  Inbox → Open → pass (P-04).

### Implementation notes (2026-11-23, US4)

- **Inbox rows open with their own "Open" button**, in place of Streamlit's pick-then-open. Every
  word in the row is platform-written (kind, title, ids, role).
- **Proposed events** are chosen by platform words (`Proposal n · run id`). The agent-written
  event id and type are shown beside the list as literal text, never in an option or a label
  (FR-010).
- **Escalation** completes the artifacts in the same grid as the Run page. The run's review
  sections follow, as in Streamlit.
- **The e2e stack seeds the escalation first**, because it moves the harness clock past T1's
  timer. Then it seeds a T2 clarification and a pending waiver.

**Checkpoint**: parity rows P-01, P-03, P-04, P-08, P-15 to P-17, P-20, P-21 and N-05 are
`passing`.

---

## Phase 7: User Story 5 – People follow delivery and check evidence (P2)

**Goal**: Use cases (with verify), Journey, Activity and Portfolio.

**Independent Test**: each page shows demo data; verify a ledger; Activity filters survive a
refresh; Journey refreshes on the configured interval.

### Tests

- [X] T056 [P] [US5] `web/src/pages/use-cases/use-cases-page.test.tsx` (P-19): the "Only mine"
  toggle (default on, kept in `?mine=`); use-case pick in `?usecase=`; runs with times and cost;
  open a run; "Open the journey view"; Verify shows checked records or "<n> break(s) found".
- [X] T057 [P] [US5] `web/src/pages/journey/journey-page.test.tsx` (P-22, P-23, N-05): the figure
  built from a journey fixture has one lane per terminal in the answer's order, a bar per run, and
  an arrow per arrow with its kind; the KPI strip shows "no data" where undefined; the escalations
  and exceptions panel; refetch every `dashboard_refresh_seconds` (fake timers, `/config.json`
  fixture); the selected use case is kept.

  Test the pure figure builder `buildJourneyFigure` directly.
- [X] T058 [P] [US5] `web/src/pages/activity/activity-page.test.tsx` (P-24) and
  `web/src/pages/portfolio/portfolio-page.test.tsx` (P-25): filters by use case, terminal, actor
  and step, kept in the address and surviving a refetch; portfolio KPIs by risk tier and status.

### Implementation

- [X] T059 [P] [US5] `web/src/pages/use-cases/use-cases-page.tsx`: port
  `src/adlc/ui/views/usecases.py`.
- [X] T060 [P] [US5] `web/src/pages/journey/build-figure.ts` (pure: port the figure logic of
  `src/adlc/ui/views/journey.py`, with lanes, bars, arrow shapes and annotations; colours from
  `status.ts`; no terminal names in code) and `web/src/pages/journey/journey-page.tsx` (Plotly
  basic bundle loaded lazily; KPI strip; panel; refresh from config; opening a run from a bar).
- [X] T061 [P] [US5] `web/src/pages/activity/activity-page.tsx` and
  `web/src/pages/portfolio/portfolio-page.tsx`: port `src/adlc/ui/views/{activity,portfolio}.py`
  (the portfolio chart through the same lazy Plotly loader).
- [X] T062 [US5] Register the four pages in `web/src/nav/registry.ts`. T056 to T058 pass.

### Implementation notes (2026-11-23, US5)

- **Figures are pure functions** (`build-figure.ts`, `build-split.ts`), tested directly. Component
  tests replace the Plotly component. `e2e/delivery.spec.ts` renders the real charts in Chromium;
  its console guard fails on any CSP violation, so the Plotly basic bundle is confirmed to work
  under `script-src 'self'`.
- **Plotly.js and margins.** Plotly.js does not turn on `automargin` the way Python Plotly's
  template did, so both figures set it; without it the lane labels were clipped (seen on a
  screenshot).
- **Escaped chart text.** Plotly interprets some HTML tags in hover and annotation text, so any
  person- or agent-written text in a figure (a rework cause) goes through `plotText()` first.
- **Use-case runs** open from their own "Open" button, as Inbox items do.

**Checkpoint**: parity rows P-19 and P-22 to P-25 are `passing`.

---

## Phase 8: User Story 6 – The CoE handles dead letters (P3)

**Goal**: the Dead letters page.

**Independent Test**: as CoE, open a payload and re-queue; as another role, see the notice and no
action.

- [X] T063 [P] [US6] `web/src/pages/dead-letters/dead-letters-page.test.tsx` (P-18, P-26): the list
  with attempts, error and re-queue count; event pick in `?event=`; payload and re-queue history
  on request; re-queue for the CoE; others see "Dead letters are handled by the CoE role." and no
  action. Whether the person is CoE is decided by the API's answer (403 or the list), never by a
  role name in code.
- [X] T064 [US6] `web/src/pages/dead-letters/dead-letters-page.tsx`: port
  `src/adlc/ui/views/dead_letters.py`, then register it. T063 passes.

**Checkpoint**: parity rows P-18 and P-26 are `passing`.

---

## Phase 9: User Story 7 – Run, check and retire the old application (P3)

**Goal**: every parity row passing, then Streamlit removed, and the platform still runs both ways.

**Independent Test**: quickstart §2, §3, §6 and §7.

- [X] T065 [P] [US7] `web/e2e/navigation.spec.ts` (N-04): back, forward and reload keep the page,
  run, use case and Activity filters; an unknown path gives "page not found"; a run without
  `?run=` gives "not found".
- [X] T066 [P] [US7] `web/e2e/a11y.spec.ts` (N-07): for every registry page, an axe scan finds no
  serious or critical issues; one keyboard-only flow (sign in, open an Inbox item, pass a run)
  works with Tab, Enter and Space only; focus lands on the page heading after navigation.
- [X] T067 [P] [US7] `web/e2e/rendering.spec.ts` (P-13): the stack seeds intake, comment,
  question, file name and artifact cell values with script and markup samples. Every page that
  shows them renders them literally, no script runs (`window.__pwned` stays undefined) and no CSP
  violation is reported.
- [X] T068 [P] [US7] `web/e2e/timing.spec.ts` (N-10, SC-007): each page shows its heading and
  first data within 2 s on the seeded stack.
- [ ] T069 [US7] Manual check of the quickstart §3 and §5 demo walk (D-1 to D-9) in current
  Chrome, Edge, Firefox and Safari. Record the result and any fixes in `contracts/parity.md`
  under "Notes". On `make demo-reset` data, also time each page's first content against the 2 s
  target (SC-007, which T068 measures only on the smaller seeded stack). Then confirm every
  parity row is `passing`.
- [ ] T070 [US7] Cutover (research R-14), in one commit:
  - **Delete:** `src/adlc/ui/`, `.streamlit/`, `tests/support/ui.py`,
    `tests/integration/ui/`.
  - **`pyproject.toml`:** remove `streamlit` and `plotly` (and the `plotly` mypy override), then
    `uv lock`.
  - **Deploy:** remove the `legacy-ui` lines from `deploy/Procfile.local` and
    `deploy/compose.yaml`, and `COPY .streamlit` from `deploy/api.Dockerfile`.
  - **Settings:** remove `legacy_ui_port` and `ADLC_LEGACY_UI_PORT` from
    `src/adlc/config/settings.py`, `.env.example` and `deploy/local.env`.
  - **Boundary tests:** `tests/unit/test_ui_boundary.py` scans only `src/adlc/web/`; replace
    `"adlc.ui"` with `"adlc.web"` in the knowledge and tools boundary lists.

  Then `git grep -nE "streamlit|adlc/ui|adlc\.ui" -- ':!specs' ':!docs'` is empty.
- [ ] T071 [US7] After cutover, run locally `make web-check` and the targeted pytest suites
  (`tests/integration/api`, `tests/integration/web`, `tests/unit/api`, the three boundary tests);
  CI runs the full `make check`. Then run `make local` and `make up` per quickstart §3 and §6
  (`docker compose exec ui which node` finds nothing).

### Implementation notes (2026-11-23, US7 automated checks)

- **Accessibility fixes from axe and the keyboard test:**
  - the muted text grey and the green, orange and grey badge text were darkened to at least
    4.8:1 (WCAG AA), with chart colours unchanged;
  - charts are captioned `<figure>`s, because Plotly's toolbar controls may not sit inside an
    "image";
  - each artifact grid is one Tab stop (the ARIA grid pattern: arrow keys inside, Tab leaves),
    so the decision is reachable from the keyboard.
- **Two real defects found and fixed, each with a regression test:**
  - a late answer to the start-up session check could undo a sign-in made meanwhile;
  - the Escalation page lost "completed" when the run reloaded with its new version.
- **Seeding:** the stub agent counts builds per terminal across runs, so the hostile
  clarification is scripted for the next T2 build.

**Checkpoint**: Streamlit is gone; the quickstart passes end to end.

---

## Phase 10: Polish & cross-cutting

- [ ] T072 [P] ADR-05 (web stack). Record it in `docs/solution-architecture.md` §17 (row "Web
  app": React browser application served by a Python ui process; ADR-05 decided 2026-11-23) and
  in the ADR list, and in `docs/build-plan.md` §4 (UI row, and the note that Streamlit was the MVP
  choice until 022) and §5 tree (`web/`, `src/adlc/web/`). The decision includes the session
  model (HttpOnly cookie plus HMAC CSRF, bearer kept for tools).
- [ ] T073 [P] `docs/solution-architecture.md` §8: the experience layer as built. Pages,
  addresses, rendering rules, and that the session never reaches page scripts.
- [ ] T074 [P] `web/README.md`: layout, commands, the page registry, rendering and boundary rules
  and their lint enforcement, file naming (kebab-case files, PascalCase component identifiers;
  constitution XIII), and how to regenerate the contract.
- [ ] T075 [P] `docs/run-without-docker.md`: the Node 24 and corepack prerequisite, `make
  web-build`, `make web-dev`, and the ports. `docs/user-manual.md`: the rebuilt pages (same
  actions; new addresses; the grid's add and remove row controls).
- [ ] T076 [P] `README.md` (repository): prerequisites and the `make` targets list.
- [ ] T077 [P] `src/adlc/api/README.md`: the `auth.py` row covers bearer *or* cookie sessions,
  the CSRF rule for cookie requests and cookie-mode sign-in, and the unchanged `PUBLIC_PATHS`.
  Add rows for `schemas/` (`ApiModel`, `extra="forbid"`, one module per router) and for
  `make openapi` and the freshness test (constitution Definition of Done: module README updated).
- [ ] T078 Run the targeted suites locally (`uv run pytest tests/integration/api
  tests/integration/web tests/unit/api tests/unit/test_ui_boundary.py`, `make web-check`). Push
  after the user's approval and let CI run `make check`.

---

## Dependencies & Execution Order

- **Setup (T001–T007)** before everything.
- **Foundational (T008–T028)** blocks every story:
  - T008 must record the goldens before T012 and T013.
  - T011 comes before T012, which comes before T013 and then T014.
  - T015 needs T001. T018 needs T014 (types).
  - T026 needs T008 and T014. T027 needs T015 and a `web-build`.
- **US1 (T029–T035)** comes after Foundational. Every later story's e2e tests need US1's
  sign-in. Their component tests use the session provider with a fixture, so they can start once
  T033 exists.
- **US2 (T036–T043)** after US1.
- **US3 (T044–T047)** after T042 (the Run page slot).
- **US4, US5 and US6** after US1. They are independent of each other and of US2 and US3, except
  that `sign-off.spec.ts`'s Inbox step (T055) needs US2.
- **US7**: T065–T068 after US1 to US6; T069 after them; T070 only when every parity row is
  `passing`; T071 after T070.
- **Polish** after T070 (the docs describe the final state); T078 last.

### Within each story

Tests first (they fail), then components, then registration, then e2e. Mark parity rows
`passing` as they pass.

## Parallel Examples

- **Foundational:** T008, T009 and T010 together; then T012's eight schema modules split across
  people; T020, T021, T022 and T023 together.
- **US1:** T029 and T030 together, then T031 and T032 (same area, in order), while T033 and T034
  proceed on the web side.
- **US2:** T036 and T037 together; T038, T039 and T040 together.
- **US4:** T048, T049 and T050 together; T051, T052 and T053 together.
- **US5:** T056, T057 and T058 together; T059, T060 and T061 together.
- **US4, US5 and US6** can run in parallel once US1 is done.

## Implementation Strategy

1. **MVP = Setup + Foundational + US1.** The API speaks cookies and typed answers, and the new
   shell signs in on 8501 while Streamlit still serves every page on 8502. The branch stays
   demo-ready.
2. **US2 + US3:** the Run page. The rebuilt application can now carry D-1 to D-3 and D-6 from a
   link.
3. **US4:** the request pages and Inbox, so D-4, D-5, D-7 and D-9 work and the demo can run fully
   in the new application.
4. **US5 + US6:** the delivery views (D-8) and dead letters.
5. **US7:** parity, cutover, docs. Streamlit is removed only when every parity row passes.
