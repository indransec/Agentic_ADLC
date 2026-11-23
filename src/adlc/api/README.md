# adlc.api

The platform API (features 001 and 007; typed answers and browser sessions since 022). It is the
only way people, and the web application, reach the platform: the web application never opens a
database connection (007 FR-020). Contracts: `specs/007-human-inbox/contracts/api.md`,
`specs/022-react-web-app/contracts/session.md` and `contracts/platform-contract.md`.

**The API reference, operation by operation: [`docs/api-reference.md`](../../../docs/api-reference.md)**,
generated from this package by `make api-docs` (part of `make openapi`).

## Modules

| Module | Purpose |
| --- | --- |
| `app.py` | `create_app`: identity provider, session check, error handlers, services, routers, tracing. |
| `auth.py` | Sessions, deny by default: every path needs one except `PUBLIC_PATHS` (`/health`, `/auth/sign-in`, unchanged by 022). A session arrives as `Authorization: Bearer` (tools, tests, pilot processes; wins when both are present) or as the browser's HttpOnly `adlc_session` cookie. A changing request (not GET, HEAD or OPTIONS) made with the cookie needs `X-ADLC-CSRF`, the session's HMAC value (`csrf_value`); otherwise `403 not_allowed`. |
| `schemas/` | 022: the answer models, one module per router. `ApiModel` refuses undeclared keys (`extra="forbid"`), so a service returning a new key fails in the tests instead of the key being dropped. Rows passed through from the store are `Record`; routes use `response_model_exclude_unset`, so keys sometimes absent stay absent. |
| `deps.py` | `Services`, built on first use: `SqlTerminalRun` with the real policy engine and stub agent and reviewer (the API never advances runs; the orchestrator worker does), `OrchestratorService`, `LedgerService` and `InboxService`. `current_actor` turns the session's person into the acting actor. |
| `docs.py` | 022: every operation's contract (area, summary, who may call it, what it does, the errors it can give), applied to the OpenAPI document as it is generated. Generating the document fails on an undocumented operation. Errors are declared as `ErrorBody`, the shape actually answered. |
| `errors.py` | One error body for every operation. |
| `routes/` | `auth` (sign-in in bearer or cookie mode, me, sign-out), `usecases` (submit, list, journey, verify), `inbox`, `runs` (detail, decisions, escalation completion), `artifacts` (edit, spreadsheet, attachments, history, download), `requests` (clarification answers, waiver decisions, dead letters), `changes`, `events`, `dashboard`. |

## Rules for every operation

- **Who acts.** The signed-in person, always. A body that names an actor, account or role is
  refused (`extra="forbid"`). Role checks live in the services, through `adlc.inbox.rules`.
- **Versions.** Decisions, edits, uploads, attachments and escalation completion carry
  `expected_version`, the run version the person saw. A different current version answers `409
  stale` and changes nothing.
- **Errors.** `{"kind", "detail", "field"?}`, never a stack trace:

  | Status | `kind` | From |
  | --- | --- | --- |
  | 401 | `not_signed_in` | No or expired session |
  | 403 | `not_allowed` | `NotAuthorised` |
  | 404 | `not_found` | Unknown use case, run, clarification, waiver, event or attachment |
  | 409 | `stale` | `StaleRun` |
  | 409 | `wrong_state` | `InvalidTransition`, `AlreadyAnswered`, `NoActiveSpecs` |
  | 422 | `invalid` | `InvalidDecision`, `InvalidUpload`, `AttachmentRefused`, `UnknownArtifact`, request validation (with `field`) |

- **Downloads.** `GET /runs/{run_id}/attachments/{content_hash}` answers only for attachments of
  that run, with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox` and `Cache-Control: private, no-store`.
- **Uploads.** At most `ADLC_ATTACHMENT_MAX` bytes are read; a larger file is refused.
- **Tracing.** Spans carry `account`, `run_id` and `usecase_id`. Request bodies are never logged
  or added to spans.

## Browser sessions (feature 022)

- **Cookie-mode sign-in.** `POST /auth/sign-in` with `"session": "cookie"` and the header
  `X-ADLC-CSRF: sign-in` sets `adlc_session` (HttpOnly, SameSite=Strict, Path=/, Max-Age to the
  session's expiry, Secure when the original scheme is https) and answers
  `{expires_at, person, csrf_token}`. The token never appears in the answer.
- **Defaults.** Without `session`, sign-in answers the bearer token exactly as before.
- **The CSRF value.** `GET /auth/me` adds `csrf_token` only for a cookie session. Sign-out with
  the cookie clears it.
- **Why the CSRF token matters.** SameSite stops other *sites*. The HMAC value stops other
  *origins* on the same host (other ports), which cannot read `/auth/me`. No CORS is ever
  answered.

## The contract and the web application (feature 022)

- `make openapi` writes `web/src/api/openapi.json` (built in-process, so `/openapi.json` stays
  behind the session) and generates the web application's types from it.
- `tests/unit/api/test_openapi_fresh.py` fails when the committed document is stale, and when any
  JSON answer is not a named model; `tests/unit/api/test_api_docs_fresh.py` does the same for
  `docs/api-reference.md`.
- `tests/integration/api/test_response_shapes.py` compares every typed route's JSON with goldens
  recorded before the models existed. Re-record only for an intended change:
  `pytest tests/integration/api/test_response_shapes.py --update-golden`.
