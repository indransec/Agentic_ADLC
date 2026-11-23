# Data Model: Web Application Rebuild (feature 022)

No table, migration or ledger record changes. The entities below live in the browser, in the
session cookie, or in the API's described answers.

## Browser session (research R-01)

| Field | Where | Rule |
| --- | --- | --- |
| `adlc_session` | Cookie, set by `POST /auth/sign-in` in cookie mode | The same signed token a bearer client gets. `HttpOnly; SameSite=Strict; Path=/`. `Max-Age` is the seconds to `expires_at`. `Secure` when the original scheme is https. |
| `expires_at` | Sign-in answer | Shown nowhere; the application treats any `401 not_signed_in` as expiry. |
| `person` | Sign-in answer, `GET /auth/me` | `account_name`, `display_name`, `roles` (as today). |

**States.**
- **Signed out → signed in:** cookie-mode sign-in with the `sign-in` CSRF header.
- **Signed in → signed out:** sign-out (the token is revoked and the cookie cleared), or expiry.
- **Revoked or expired:** every request answers `401 not_signed_in`. The application clears its
  in-memory person and CSRF value and opens `/sign-in?next=…`.

**Invariant.** The token never appears in an answer body, browser storage, the address or a log
(FR-013).

## CSRF value (research R-02)

| Field | Rule |
| --- | --- |
| `csrf_token` | `base64url(HMAC-SHA256(session_secret, "csrf\0" + token))`. Returned by cookie-mode sign-in and by `GET /auth/me` when the request came with the cookie. Held in memory only. |
| `X-ADLC-CSRF` | Required on every cookie-authenticated request that is not GET, HEAD or OPTIONS. Compared in constant time. The value `sign-in` is required on cookie-mode sign-in. |

A missing or wrong value answers `403 not_allowed`, "cross-site request refused". Bearer
requests are not checked.

## Page registry entry (research R-09, FR-002)

| Field | Type | Rule |
| --- | --- | --- |
| `id` | string | kebab-case, unique (`inbox`, `new-use-case`, `run`, …) |
| `title` | string | As today's page title |
| `section` | `"Work" \| "Delivery" \| "Insights" \| "Operations" \| null` | `null` for pages opened from other pages |
| `path` | string | See contracts/pages.md |
| `icon` | string | Icon name shown in the sidebar |
| `inSidebar` | boolean | false for Run, Clarification, Escalation, Waiver |
| `params` | list of query parameter names | Kept in the address (FR-003) |
| `component` | lazy page component | — |

Sidebar order is the order of the table. A later mode adds an optional field (for example
`modes`) and a filter; nothing else changes.

## Runtime settings (research R-12)

`GET /config.json` from the ui process:

| Field | Source | Rule |
| --- | --- | --- |
| `env` | `ADLC_ENV` | `"dev" \| "demo" \| null`; drives the environment badge |
| `dashboard_refresh_seconds` | `ADLC_UI_DASHBOARD_REFRESH` | Positive integer; Journey and Activity refresh interval |

New setting (ui process only): `ADLC_UI_DIST_DIR`, the path to the built files, default
`web/dist`. Temporary until cutover: `ADLC_LEGACY_UI_PORT`, default 8502 (R-14).

## Platform contract (research R-04, R-05)

- **`ApiModel`**: the base for every answer model. `extra="forbid"`, so an undeclared key
  returned by a service fails the request in tests instead of being dropped.
- **Answer models**: one per answer of the 25 untyped routes, grouped by router under
  `adlc.api.schemas`. Open-ended content (artifact rows, cells, payloads) uses `JsonValue`.
- **`web/src/api/openapi.json`**: generated, committed. **`web/src/api/schema.d.ts`**:
  generated, committed. Both are checked for freshness (FR-021).
- **Error answer**: unchanged, `{"kind", "detail", "field"?}`. The web client maps `kind` to
  behaviour:

  | kind | Status | Application behaviour |
  | --- | --- | --- |
  | `not_signed_in` | 401 | Go to sign-in with `next` |
  | `not_allowed` | 403 | Plain-words refusal; the CSRF refusal is reported the same way |
  | `not_found` | 404 | "Not found" page state with a link back |
  | `stale` | 409 | Reload the run and show the stale message (R-07, R-08) |
  | `wrong_state` | 409 | Plain-words refusal |
  | `invalid` | 422 | Shown beside `field` when given, otherwise as a page message |
  | `unavailable` | 502 (ui process) | "The platform could not be reached"; keep input; retry on interval |

## Parity checklist row (FR-026)

| Field | Rule |
| --- | --- |
| `page` / `action` | One row per page and per action on it |
| `today` | The Streamlit behaviour, citing the `AppTest` test where one exists |
| `rebuilt` | The test id(s) that show the same behaviour |
| `status` | `open` / `passing`; every row `passing` before cutover |

The rows are in contracts/parity.md.
