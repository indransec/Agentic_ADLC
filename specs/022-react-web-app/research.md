# Research: Web Application Rebuild (feature 022)

Context found while planning:

- SA §17 chose "FastAPI backend + React frontend" for the web app. Build plan §4 replaced it with
  Streamlit for the MVP "to keep the stack Python-only … a React UI can replace it later". This
  feature takes that later step and records ADR-05 (web stack), which SA §17 lists as still to be
  recorded.
- The API on this branch has 31 routes. Sign-in, me and health have typed answers, and three
  return raw responses (attachment download, sign-out, re-queue). The other 25 answer
  `dict[str, Any]` or `list[dict[str, Any]]`, so the OpenAPI document says nothing about their
  shape.
- Sessions are signed, expiring tokens from `LocalIdentityProvider` (`adlc.identity.sessions`),
  revoked in-process at sign-out. Auth is a middleware (`adlc.api.auth.install_auth`) that reads
  only `Authorization: Bearer`. `PUBLIC_PATHS = {"/health", "/auth/sign-in"}`.
- Errors have one shape, `{"kind", "detail", "field"?}` (`adlc.api.errors`). Stale versions are
  `409 stale`.
- The Streamlit UI tests (`tests/integration/ui/`, 11 files, about 660 lines) drive the app
  through `AppTest` against the real API over the orchestration harness (`tests/support/ui.py`).
- Node 24 is available locally; pnpm is not installed (corepack provides it).

## R-01 Session held in an HttpOnly cookie, bearer kept

**Decision.** `POST /auth/sign-in` takes an optional `session` field: `"bearer"` (the default,
today's answer, unchanged) or `"cookie"`.

- In cookie mode the answer leaves out `token` and sets `adlc_session=<token>` with the
  attributes `HttpOnly; SameSite=Strict; Path=/; Max-Age=<seconds to expires_at>`. It adds
  `Secure` when the original request was https (R-03 passes the scheme on).
- The middleware reads `Authorization: Bearer` first and the cookie second. A request that carries
  neither is refused as today.
- `IdentityProvider` does not change: the cookie holds the same signed token, so expiry and
  revocation behave exactly as for bearer clients (FR-015).
- Sign-out revokes the token and clears the cookie (`Max-Age=0`).

**Rejected.**
- A backend-for-frontend that holds the token server-side and keys a second cookie to it: this
  adds a session store to the ui process, plus a second expiry and revocation path, for no gain
  over HttpOnly.
- A token in `localStorage` or memory: page scripts could read it (FR-013, SC-003).
- A separate `/auth/browser-sign-in` path: it would add to `PUBLIC_PATHS` (FR-016).

## R-02 Cross-site request protection: a session-bound token plus a custom header

**Decision.** A request authenticated by the cookie whose method is not GET, HEAD or OPTIONS must
carry `X-ADLC-CSRF: <value>`. The value is
`base64url(HMAC-SHA256(session_secret, "csrf\0" + session token))`, compared in constant time.

- The application learns the value from the cookie-mode sign-in answer and from `GET /auth/me`.
  `/auth/me` adds `csrf_token` only when the request came with the cookie.
- Bearer requests need no CSRF token, because browsers never attach them automatically.
- Cookie-mode sign-in has no session yet. It must carry the custom header
  `X-ADLC-CSRF: sign-in`; without it the request is refused, which blocks login CSRF.
- A missing or wrong value answers `403 {"kind": "not_allowed", "detail": "cross-site request
  refused"}`.

This works because the platform opens no CORS (FR-017). Another origin therefore cannot read
`/auth/me` or send a custom header without a preflight that fails. SameSite=Strict stops the
cookie from being sent from other *sites*. The HMAC token covers other *origins* on the same site,
such as other ports on the same host (see "Rejected" below). The CSRF value is not a session credential: it is useless without the HttpOnly
cookie.

**Rejected.**
- Double-submit with a second readable cookie: a cookie is shared across ports on the same host
  (local runs put the API on :8000 and the app on :8501), so a plain cookie is weaker than an HMAC
  bound to the session.
- SameSite alone: it does not cover older browsers or subdomain cases. More importantly, every
  other service on the same host counts as the same *site*, whatever its port (Phoenix on :6006,
  the pilot hosts, the lab). A page served by any of them, if compromised, would get the cookie
  sent by SameSite=Strict. It is still a different *origin*, so it cannot read `/auth/me` and
  cannot learn the HMAC value. The token is therefore the control that matters on a shared host,
  not an extra.

**Note.** Cookies ignore ports, so on `127.0.0.1` the browser also sends `adlc_session` to the
API's own port. That is harmless: the request is still same-site and still needs the CSRF header
to change anything.

## R-03 The ui process: Python, serving the built files and proxying `/api`

**Decision.** A new package `adlc.web`, a Starlette application run by uvicorn (both already
dependencies, through FastAPI) with the console script `adlc-web`. It serves:

| Path | Answer |
| --- | --- |
| `/api/{path}` | Streams the request to `ADLC_API_URL/{path}` and streams the answer back |
| `/config.json` | Runtime settings for the page (R-12) |
| `/health` | `{"status": "ok"}` and whether the built files are present |
| `/assets/*` | Built files, `Cache-Control: public, max-age=31536000, immutable` (hashed names) |
| anything else | `index.html`, `Cache-Control: no-cache` (client-side routes) |

- **Headers forwarded.** Request headers come from an allowlist: `cookie`, `content-type`,
  `content-length`, `accept`, `x-adlc-csrf`, plus `x-forwarded-proto` and `x-forwarded-host` set
  by the proxy. Response headers come from an allowlist: `set-cookie`, `content-type`,
  `content-disposition`, `cache-control`, `content-length`, `x-content-type-options`.
- **Errors.** If the API is down, the answer is `502 {"kind": "unavailable", "detail": "the
  platform could not be reached"}` in the platform's error shape.
- **Logging.** Paths and status only, never headers or bodies (constitution XI).
- **Platform unchanged.** The API's paths do not change, and the ui process's own paths never
  reach the API, so `PUBLIC_PATHS` stays as it is (FR-016, FR-017).
- **Settings.** It reads `UiSettings` (existing `ADLC_API_URL`, `ADLC_UI_PORT`,
  `ADLC_UI_DASHBOARD_REFRESH`, `ADLC_ENV`) plus a new `ADLC_UI_DIST_DIR`, default `web/dist`.
- **Boundary.** `adlc.web` imports only `adlc.web` and `adlc.config`, enforced by the existing
  boundary test pointed at the new package.

**Rejected.**
- The API mounting the static files: these paths would need to be public, which breaks FR-016;
  it would also mix web serving into the platform process.
- nginx or Caddy: a new non-Python runtime service, against FR-022 and the branch's all-Python
  runtime.
- The Vite dev server in demo: it is a dev tool only, used in development behind the same `/api`
  proxy rule.

## R-04 Typed answers for every route

**Decision.** Pydantic models for the 25 untyped routes, one module per router under
`src/adlc/api/schemas/` (`runs.py`, `artifacts.py`, `inbox.py`, `usecases.py`, `requests.py`,
`changes.py`, `events.py`, `dashboard.py`). Each route sets `response_model`.

- **No silent drops.** Every model derives from `ApiModel`, with `extra="forbid"` and
  `strict=False`. Validating a service's dict against it therefore fails loudly if the service
  returns a key the model does not declare. Plain FastAPI would drop the key, and the
  application would lose data without warning.
- **Behaviour unchanged.** Before the models go in, a golden test records the JSON each route
  returns on the harness's scripted walk (`tests/integration/api/test_response_shapes.py`). The
  same test must pass unchanged after (FR-015, SC-006).
- **Contract sources.** The shapes start from `specs/007-human-inbox/contracts/api.md` and
  `specs/013-lifecycle-dashboard/contracts/api-dashboard.md`, checked against the code.
- **Open-ended fields.** Artifact rows, cells and event payloads are open by nature. They are typed
  as `list[dict[str, JsonValue]]` or `JsonValue`, not invented structure.

**Rejected.**
- Hand-written TypeScript types: they drift silently.
- Typing only the routes the app uses: the app uses all 25.

## R-05 One contract file, generated types, freshness checked twice

**Decision.**
- `scripts/export_openapi.py` writes `create_app(...).openapi()` to `web/src/api/openapi.json`. It
  runs in-process, so `/openapi.json` stays behind the session.
- `openapi-typescript` (MIT) turns that file into `web/src/api/schema.d.ts`.
- `openapi-fetch` (MIT) is the typed client used by `web/src/api/client.ts`.
- `make openapi` runs both steps.
- **Freshness, Python side:** `tests/unit/api/test_openapi_fresh.py` compares the live schema with
  the committed JSON, so it runs without Node.
- **Freshness, web side:** `web-typecheck` regenerates `schema.d.ts` into a temporary file and
  diffs it.

Either drift fails `make check` (FR-021, SC-008).

## R-06 Browser stack and licences

| Package | Use | Licence |
| --- | --- | --- |
| React, React DOM | Views | MIT |
| TypeScript | Language, strict mode | Apache-2.0 |
| Vite | Dev server, build | MIT |
| React Router | Client-side routes, address state | MIT |
| TanStack Query | Fetching, caching, interval refresh | MIT |
| AG Grid Community (`ag-grid-community`, `ag-grid-react`) | Artifact editor and large tables | MIT |
| Plotly.js basic bundle (`plotly.js-basic-dist-min`) | Journey lanes and portfolio charts | MIT |
| openapi-typescript, openapi-fetch | Contract types, typed client | MIT |
| Vitest | Unit and component tests | MIT |
| Testing Library (`@testing-library/react`, `user-event`, `jest-dom`) | Component tests | MIT |
| MSW | Typed API mocks in component tests | MIT |
| Playwright (`@playwright/test`) | End-to-end tests | Apache-2.0 |
| `@axe-core/playwright` | Accessibility checks in end-to-end tests | MPL-2.0 |
| ESLint, typescript-eslint, `eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y`, `eslint-plugin-unicorn` (`filename-case`: kebab-case) | Lint | MIT |
| Prettier | Formatting | MIT |
| pnpm | Package manager (via corepack, `packageManager` field) | MIT |
| Node.js 24 LTS | Build only | MIT |

All are OSI-approved. MPL-2.0 is file-level copyleft, used only by test code, never shipped.
Versions are pinned exactly in `web/package.json`, and `pnpm-lock.yaml` is committed.

**AG Grid over TanStack Table.** AG Grid edits, adds and removes rows, and virtualises 1,000 rows
out of the box. TanStack Table is headless, so cell editing, keyboard navigation and accessibility
would be ours to write and test. Only the Community edition (MIT) is used: no Enterprise modules,
no licence key.

**Plotly.js basic bundle.** It has the same chart model as today's Python Plotly figures
(scatter, bar, shapes, annotations), so the lanes and arrows port figure by figure. The basic
bundle has no WebGL traces and needs no `unsafe-eval`, which keeps the CSP strict (R-11).
Recharts was rejected: it has no arrows or shapes between lanes without custom SVG.

## R-07 Data fetching, refresh and input safety

**Decision.** TanStack Query holds every read.

- The Inbox uses `refetchInterval: 30_000`. Journey and Activity use the configured dashboard
  interval (R-12).
- `refetchIntervalInBackground: false`, so a hidden tab stops polling, and only one refresh runs
  at a time (FR-004, edge case).
- Form state is component state, separate from query data, so a refresh never resets typing.
- Mutations invalidate the run, the inbox and the use-case queries they affect.
- On a `409 stale` answer, the run is refetched and the stale message is shown. The person's
  unsaved grid edits are discarded with that message, matching today's "check it and act again"
  (FR-006).

## R-08 Run version semantics

**Decision.** Today the Run page sends the version shown on the page before the click, not the
freshly fetched one (`run.py:load`, "seen"). The rebuilt page keeps the version from the last
render in a ref and sends that as `expected_version`. A background refetch that brings a newer
version updates the page and shows "This run changed"; it does not quietly move the version the
person is acting on. This keeps the 007 FR-011 guarantee.

## R-09 Addresses and the page registry

**Decision.**
- **Registry.** One typed table, `web/src/nav/registry.ts`, holds every page: id, title, section,
  path, icon, `inSidebar`, `params` and `component`. The sidebar, the router and
  `navigate()` are all built from it (FR-002). A later console mode would add a field and filter
  the same table.
- **Ids in the address.** All ids travel as query parameters, because run ids contain `/`
  (`UC-0042/T3/run-2`). See contracts/pages.md for the full address list.
- **Old links.** `/?run=<id>` redirects to `/run?run=<id>`, so existing evidence links keep
  working.
- **Sign-in redirect.** Pages need a session. A page opened without one goes to
  `/sign-in?next=<original address>`, and after sign-in only a same-origin relative `next` is
  followed (no open redirect).

## R-10 Tests that replace the Streamlit suite

**Decision.** Three layers:

1. **Component tests** (Vitest, Testing Library, MSW), next to the code as `*.test.tsx`.
   - MSW handlers are typed by `schema.d.ts`, so a mock that no longer matches the platform fails
     type-checking.
   - Each existing `AppTest` file gets an equivalent (contracts/parity.md), for example
     `test_rendering.py` → `web/src/ui/text.test.tsx` and page tests that feed markup and script
     samples into every text field.
2. **API tests (Python)** for the new session and CSRF rules and the response models:
   `tests/integration/api/test_cookie_session.py`, `test_csrf.py`, `test_response_shapes.py`.
   Plus `tests/integration/web/test_server.py` for `adlc.web`: proxying, header allowlist, static
   files, fallback, `/config.json`, CSP headers, and 502 when the API is down.
3. **End-to-end** (Playwright, Chromium) against a real stack started by
   `tests/e2e/stack.py`.
   - The stack is the API and `adlc-web` over a fresh harness database with stub agents and a
     drain loop. It is seeded with known runs: one awaiting decision, a 1,000-row and a 1,001-row
     artifact, a clarification, an escalation, a waiver and a dead letter. This is deterministic,
     with no model calls.
   - Flows: sign-in and redirect, intake, sign-off (pass and rework), artifact edit and save,
     stale version, expired session, a cross-site request refused, attachment download only, and
     keyboard-only use with an axe scan per page.

The parity checklist (contracts/parity.md) is the condition for removing Streamlit (FR-026).

**Rejected.**
- Running only against `make local`: it starts real agents and model calls, so it is not
  deterministic.
- Keeping `AppTest`: it disappears with Streamlit.

## R-11 Browser security headers

**Decision.** `adlc.web` sets these on every answer:
- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'
  'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none';
  frame-ancestors 'none'; form-action 'self'`. Inline styles are needed by AG Grid and Plotly's
  layout; scripts stay strict.
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `Cross-Origin-Opener-Policy: same-origin`.

An end-to-end test fails on any CSP violation reported in the console.

**Rendering safety.** ESLint makes the following errors:
- `react/no-danger` (no `dangerouslySetInnerHTML`);
- `no-restricted-properties` for `innerHTML` and `outerHTML`;
- `no-restricted-globals` for `fetch` and `XMLHttpRequest` outside `src/api/client.ts`, with an
  override for that file;
- `no-restricted-imports` for `openapi-fetch` outside `src/api/` (FR-018).

Agent and person text is shown through one `<Literal>` component (`white-space: pre-wrap`,
`overflow-wrap: anywhere`), never inside `<label>`, `aria-label` or `title` (FR-010).

**Attachments.** The client fetches the bytes and hands the browser a `Blob` of type
`application/octet-stream` with a `download` attribute, so nothing is rendered inline, whatever
the stored media type (FR-012). The API already sends `Content-Disposition: attachment`.

## R-12 Runtime settings for the page

**Decision.** `GET /config.json` on the ui process answers `{"env": "dev"|"demo"|null,
"dashboard_refresh_seconds": n}` from `UiSettings`. It holds no secret. It is read once at start,
so one build serves every environment. Nothing environment-specific is baked into the bundle.

## R-13 Running and building

- **Local (`make local`).** `local-setup` runs `make web-build` (pnpm install with a frozen
  lockfile, then `vite build`). The Procfile's `ui` line becomes `uv run adlc-web` on
  `ADLC_UI_PORT`. Development mode is `make web-dev`: Vite on :5173, proxying `/api` and
  `/config.json` to `adlc-web`.
- **Containers.** `deploy/api.Dockerfile` gains a first stage, `FROM node:24-slim AS web`, which
  copies `web/` and runs `pnpm install --frozen-lockfile && pnpm build`. The Python stage copies
  `/web/dist` to `/app/web/dist`. The compose `ui` service runs `adlc-web`, and its health check
  calls `http://127.0.0.1:8501/health`. No Node at runtime (FR-022).
- **CI.** `.github/workflows/ci.yml` adds `actions/setup-node` (Node 24, pnpm cache), runs
  `corepack enable`, and installs Playwright's Chromium. `make install` adds `pnpm install
  --frozen-lockfile` in `web/`.
- **`make check`.** It gains `web-check`, which runs `web-lint` (ESLint and Prettier check),
  `web-typecheck` (`tsc --noEmit` plus the schema freshness diff), `web-test` (Vitest with
  coverage) and `web-e2e` (Playwright) (FR-024).

## R-14 Side-by-side period and cutover

**Decision.**
- **Side by side.** From the first web slice, `adlc-web` takes `ADLC_UI_PORT` (8501) and Streamlit
  moves to the temporary `ADLC_LEGACY_UI_PORT` (default 8502), in both the Procfile and compose.
  The final state then needs no port change (FR-023).
- **Cutover.** When every parity row passes, one commit removes:
  - `src/adlc/ui/` (except what moved to `adlc.web`), `.streamlit/` and `tests/support/ui.py`;
  - `tests/integration/ui/` and the `streamlit` and `plotly` dependencies;
  - the mypy override for plotly, `ADLC_LEGACY_UI_PORT`, and the Dockerfile's `.streamlit` copy.

  The boundary test then checks `adlc.web` only.
- **Settings.** `UiSettings` stays: it is the ui process's settings, and the name still fits.

## R-15 What is not built (constitution XII, post-MVP)

Operations console mode and the board link (in scope only on `main`); mobile layouts; dark theme;
internationalisation; SSO or OIDC; server-side rendering; offline use; real-time push (polling is
kept).
