# adlc.api

The platform API (features 001 and 007). It is the only way people, and the web application,
reach the platform: the web application never opens a database connection (007 FR-020).
Contract: `specs/007-human-inbox/contracts/api.md`.

## Modules

| Module | Purpose |
| --- | --- |
| `app.py` | `create_app`: identity provider, session check, error handlers, services, routers, tracing. |
| `auth.py` | Bearer sessions. Every path needs one except `PUBLIC_PATHS` (`/health`, `/auth/sign-in`). |
| `deps.py` | `Services`, built on first use: `PostgresTerminalRun` with the real policy engine and stub agent and reviewer (the API never advances runs; the orchestrator worker does), `OrchestratorService`, `LedgerService` and `InboxService`. `current_actor` turns the session's person into the acting actor. |
| `errors.py` | One error body for every operation. |
| `routes/` | `usecases` (submit, list, journey, verify), `inbox`, `runs` (detail, decisions, escalation completion), `artifacts` (edit, spreadsheet, attachments, history, download), `requests` (clarification answers, waiver decisions, dead letters). |

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
