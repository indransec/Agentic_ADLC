# Platform API reference

ADLC Platform API, version 0.1.0.

> Generated from the API's OpenAPI document by `make api-docs` (`scripts/api_docs.py`); do not edit by hand. Each operation's contract is in `src/adlc/api/docs.py`, its inputs in the route's request models, its answers in `src/adlc/api/schemas/`. The same document gives the web application its types (`web/src/api/openapi.json`).

## Overview

### Where the API is

| Who | Base address |
| --- | --- |
| The browser application | `/api` on the web application's own address (`adlc-web` forwards it, unchanged) |
| Tools, tests, pilot processes | The API directly: `http://api:8000` in compose, `http://127.0.0.1:8000` locally |

Every path below is relative to the base. The API never answers CORS: a page on another origin
cannot call it from a browser.

### Sessions

Every operation needs a session except `GET /health` and `POST /auth/sign-in`.

- **Bearer** (tools, tests, pilot processes): sign in without `session` (or with `"bearer"`), then
  send `Authorization: Bearer <token>`.
- **Cookie** (the browser application): sign in with `"session": "cookie"` and the header
  `X-ADLC-CSRF: sign-in`. The answer sets the HttpOnly, SameSite=Strict cookie `adlc_session` and
  carries `csrf_token`; `GET /auth/me` also gives it. Every changing request (not GET, HEAD or
  OPTIONS) made with the cookie must send that value in `X-ADLC-CSRF`, or it is refused with `403`.
  Page scripts never see the session itself.
- A bearer header wins when both are present. Sessions expire after `ADLC_SESSION_TTL`; sign-out
  revokes them.

### Who acts

Always the signed-in person. A body that names an actor, account or role is refused (`422`).
Decision rights come from the pinned terminal specs and the role catalogue, and are checked on
every operation: hiding an action in a client is a convenience, never the control.

### Versions

Decisions, artifact edits, uploads, attachments and escalation completion send
`expected_version`: the run version the person saw (`run.version` in the run detail). If the run
changed meanwhile the answer is `409` with `kind` `stale`, and nothing is recorded; reload the run
and act again.

### Errors

Every refusal has one shape, [`ErrorBody`](#schema-errorbody):
`{"kind": "...", "detail": "...", "field": "..."}` (`field` only when one input is at fault).
Never a stack trace.

| Status | `kind` | Meaning |
| --- | --- | --- |
| 401 | `not_signed_in` | No session, or it expired or was revoked |
| 403 | `not_allowed` | The person may not do this; or a cookie session's change came without its CSRF value (`cross-site request refused`) |
| 404 | `not_found` | No such use case, run, request, event or file |
| 409 | `stale` | The run changed since the version sent |
| 409 | `wrong_state` | Not possible in the current state, or already decided |
| 422 | `invalid` | The input was refused |

Each operation lists the statuses it can answer.

### Conventions

- **Run ids contain `/`** (`UC-0001/T1/run-1`). In a path they may be sent as is or encoded
  (`UC-0001%2FT1%2Frun-1`).
- **Times** are ISO 8601 in UTC.
- **Money** (`cost_usd` in run and use-case costs) is a decimal string, such as `"0.0125"`.
- **Values from specs and catalogues** (outcomes, root causes, terminal ids, roles, states) are
  plain strings: the platform names none of them in code.
- **Text written by people or agents** (intake, comments, reasons, findings, answers, file names,
  artifact cells) is data. Clients must show it as text, never as markup.
## Operations

| Area | Operation | What it does |
| --- | --- | --- |
| Health | [`GET /health`](#op-get-health) | Service health |
| Sessions | [`POST /auth/sign-in`](#op-post-auth-sign-in) | Sign in |
| Sessions | [`POST /auth/sign-out`](#op-post-auth-sign-out) | Sign out |
| Sessions | [`GET /auth/me`](#op-get-auth-me) | Who is signed in |
| Use cases | [`POST /usecases`](#op-post-usecases) | Submit a use case |
| Use cases | [`GET /usecases`](#op-get-usecases) | List use cases |
| Use cases | [`POST /usecases/{usecase_id}/verify`](#op-post-usecases-usecase-id-verify) | Verify the use case's evidence ledger |
| Use cases | [`GET /usecases/{usecase_id}`](#op-get-usecases-usecase-id) | A use case's journey |
| Inbox | [`GET /inbox`](#op-get-inbox) | What is waiting for me |
| Runs | [`POST /runs/{run_id}/decisions`](#op-post-runs-run-id-decisions) | Decide on a run |
| Runs | [`POST /runs/{run_id}/escalation`](#op-post-runs-run-id-escalation) | Complete an escalated run |
| Runs | [`GET /runs/{run_id}`](#op-get-runs-run-id) | A run's detail and decision form |
| Artifacts | [`PUT /runs/{run_id}/artifacts/{artifact_id}`](#op-put-runs-run-id-artifacts-artifact-id) | Edit an artifact |
| Artifacts | [`POST /runs/{run_id}/artifacts/{artifact_id}/spreadsheet`](#op-post-runs-run-id-artifacts-artifact-id-spreadsheet) | Replace a table from a spreadsheet |
| Artifacts | [`POST /runs/{run_id}/artifacts/{artifact_id}/attachments`](#op-post-runs-run-id-artifacts-artifact-id-attachments) | Attach a file to an artifact |
| Artifacts | [`GET /runs/{run_id}/artifacts/{artifact_id}/history`](#op-get-runs-run-id-artifacts-artifact-id-history) | An artifact's versions |
| Artifacts | [`GET /runs/{run_id}/attachments/{content_hash}`](#op-get-runs-run-id-attachments-content-hash) | Download an attachment |
| Requests | [`POST /clarifications/{clarification_id}/answers`](#op-post-clarifications-clarification-id-answers) | Answer a clarification |
| Requests | [`POST /waivers/{waiver_id}/decision`](#op-post-waivers-waiver-id-decision) | Approve or reject a waiver |
| Requests | [`GET /dead-letters`](#op-get-dead-letters) | List dead-lettered events |
| Requests | [`GET /dead-letters/{event_id}`](#op-get-dead-letters-event-id) | A dead letter's payload and history |
| Requests | [`POST /dead-letters/{event_id}/requeue`](#op-post-dead-letters-event-id-requeue) | Re-queue a dead letter |
| Changes | [`GET /changes`](#op-get-changes) | Change requests waiting for a decision |
| Changes | [`POST /changes/{change_id}/decision`](#op-post-changes-change-id-decision) | Approve or reject a change request |
| Proposed events | [`GET /events/proposed`](#op-get-events-proposed) | Proposed events waiting for me |
| Proposed events | [`POST /events/proposed/{usecase_id}/{terminal_id}/{run_number}/{event_id}`](#op-post-events-proposed-usecase-id-terminal-id-run-number-event-id) | Confirm or dismiss a proposed event |
| Dashboard | [`GET /dashboard/usecases/{usecase_id}/journey`](#op-get-dashboard-usecases-usecase-id-journey) | A use case's journey view |
| Dashboard | [`GET /dashboard/usecases/{usecase_id}/kpis`](#op-get-dashboard-usecases-usecase-id-kpis) | A use case's KPIs |
| Dashboard | [`GET /dashboard/portfolio`](#op-get-dashboard-portfolio) | KPIs across use cases |
| Dashboard | [`GET /dashboard/activity`](#op-get-dashboard-activity) | The activity feed |
| Dashboard | [`GET /dashboard/runs/{run_id}/timeline`](#op-get-dashboard-runs-run-id-timeline) | A run's step timeline |

## Health

Is the API up and can it reach its database.

<a id="op-get-health"></a>

### `GET /health`

**Service health.**

Public. `200` with every check `ok`, or `503` with the failing check `unavailable`.

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`Health`](#schema-health) (`application/json`) | OK |
| 503 | [`Health`](#schema-health) (`application/json`) | A check failed: the body says which |

## Sessions

Sign in (a bearer token, or the browser's HttpOnly cookie), who is signed in, sign out.

<a id="op-post-auth-sign-in"></a>

### `POST /auth/sign-in`

**Sign in.**

Public. With `session` omitted or `"bearer"`, answers a bearer token for the `Authorization` header (tools, tests, pilot processes). With `"cookie"` (the browser application) the request must carry `X-ADLC-CSRF: sign-in`; the answer sets the HttpOnly, SameSite=Strict cookie `adlc_session` and carries the session's CSRF value instead of the token. A wrong account or password answers `401` without saying which.

**Request body** (`application/json`, required)

[`SignInRequest`](#schema-signinrequest)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `account_name` | string | yes | at least 1 characters; at most 40 characters |
| `password` | string (password) | yes | at least 1 characters |
| `session` | `"bearer"` or `"cookie"` | no | `bearer`: answer a token. `cookie` (the browser): set the HttpOnly session cookie; needs the header `X-ADLC-CSRF: sign-in` (default `bearer`) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`SignInResponse`](#schema-signinresponse) or [`BrowserSignInResponse`](#schema-browsersigninresponse) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-post-auth-sign-out"></a>

### `POST /auth/sign-out`

**Sign out.**

Revokes the session. For a cookie session the answer also clears the cookie.

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 204 | none | Done; no body |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |

<a id="op-get-auth-me"></a>

### `GET /auth/me`

**Who is signed in.**

Any signed-in person. The person's account, name and roles; for a cookie session also `csrf_token`, the value every changing request must send in `X-ADLC-CSRF`.

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`MeOut`](#schema-meout) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |

## Use cases

Submit a use case, list them, follow one, verify its evidence ledger.

<a id="op-post-usecases"></a>

### `POST /usecases`

**Submit a use case.**

A person in a role allowed to submit (the role catalogue's submitters; anyone when none is configured). Pins the active terminal specs and opens the first terminal's run.

**Request body** (`application/json`, required)

[`Submission`](#schema-submission)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | A short name (at least 1 characters; at most 200 characters) |
| `intake_text` | string | yes | The problem, the people involved and the outcome wanted, in the submitter's words (at least 1 characters; at most 20000 characters) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 201 | [`Submitted`](#schema-submitted) (`application/json`) | Created |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-usecases"></a>

### `GET /usecases`

**List use cases.**

Any signed-in person. Newest first, with each one's count of open runs. `mine=true`: those the person submitted or takes part in through a role of one of its runs.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `mine` | query | boolean | no | Only those I submitted or take part in through a role (default `false`) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | array of [`UseCaseListItem`](#schema-usecaselistitem) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-post-usecases-usecase-id-verify"></a>

### `POST /usecases/{usecase_id}/verify`

**Verify the use case's evidence ledger.**

Any signed-in person. Re-computes the hash chain of the use case's ledger records and lists any break. The verification is itself recorded, under the person.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `usecase_id` | path | string | yes | A use case, such as `UC-0001` |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`Verification`](#schema-verification) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-usecases-usecase-id"></a>

### `GET /usecases/{usecase_id}`

**A use case's journey.**

Any signed-in person. The use case, all its runs, per-terminal time and rework summary, and model cost.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `usecase_id` | path | string | yes | A use case, such as `UC-0001` |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`UseCaseJourney`](#schema-usecasejourney) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

## Inbox

Everything waiting for the signed-in person.

<a id="op-get-inbox"></a>

### `GET /inbox`

**What is waiting for me.**

Any signed-in person. Sign-offs, clarifications, escalations, waivers and blocked runs addressed to one of the person's roles (and dead letters for the CoE role), soonest due first.

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | array of [`InboxItem`](#schema-inboxitem) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |

## Runs

A terminal run's detail and the decisions people take on it.

<a id="op-post-runs-run-id-decisions"></a>

### `POST /runs/{run_id}/decisions`

**Decide on a run.**

A person in a sign-off role of the run (the spec's status rights); `terminate` also for the roles the spec allows to terminate. Sends `expected_version`, the version the person saw. `rework` needs `root_cause` (and `target_terminal` where the cause's route resolves a terminal); `exception` needs the spec's waiver fields and opens a waiver; `pass` needs the emitted values the spec asks people to type. A decision that differs from the reviewer's recommendation needs a `reason`. Rights are checked on every decision.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |

**Request body** (`application/json`, required)

[`Decision`](#schema-decision)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `decision` | `"pass"` or `"rework"` or `"exception"` or `"terminate"` | yes | The outcome; offered per person in the run detail's `form.outcomes` |
| `comment` | string or null | no | Why (rework and terminate) (at most 4000 characters) |
| `root_cause` | string or null | no | Rework only: one of `form.root_causes` (at most 100 characters) |
| `reason` | string or null | no | Needed when the decision differs from the reviewer's recommendation (at most 2000 characters) |
| `fields` | object | no | Values the outcome needs (`form.requires`, `form.typed_fields`, or `alternative` on pass) |
| `target_terminal` | string or null | no | Rework only, for causes in `form.target_terminal_for`: the owning terminal (at most 20 characters) |
| `expected_version` | integer | yes | The run version the person saw (≥ 0) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunSummary`](#schema-runsummary) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-post-runs-run-id-escalation"></a>

### `POST /runs/{run_id}/escalation`

**Complete an escalated run.**

A person in one of the terminal's accountable roles, while the run is escalated. Supplies the artifacts the agents could not finish; the run then goes to normal sign-off. Sends `expected_version`.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |

**Request body** (`application/json`, required)

[`Completion`](#schema-completion)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `artifacts` | object (string → array of object) | yes | Rows per artifact id, for the artifacts the agents could not finish |
| `expected_version` | integer | yes | The run version the person saw (≥ 0) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunSummary`](#schema-runsummary) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-runs-run-id"></a>

### `GET /runs/{run_id}`

**A run's detail and decision form.**

Any signed-in person. Everything SA §8.2 asks for on one page: the run, its artifacts and versions, prerequisites, control results, the reviewer's recommendation, prior rework, clarifications, approvals, waiver, timer, cost, timeline and evidence; and `form`, what this person may decide and what each outcome needs (built from the pinned spec).

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunDetail`](#schema-rundetail) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

## Artifacts

Edit a run's artifacts, upload spreadsheets, attach and download files, see versions.

<a id="op-put-runs-run-id-artifacts-artifact-id"></a>

### `PUT /runs/{run_id}/artifacts/{artifact_id}`

**Edit an artifact.**

A person in a sign-off or accountable role of the run, while it awaits sign-off or is escalated. Replaces the artifact's rows with a new version (the run's controls re-run); `changed` is false when the rows were identical. Sends `expected_version`.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |
| `artifact_id` | path | string | yes | An artifact id of the run's terminal spec, such as `kpis` |

**Request body** (`application/json`, required)

[`Edit`](#schema-edit)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `rows` | any JSON | yes | The artifact's new rows (a table) or text |
| `expected_version` | integer | yes | The run version the person saw (≥ 0) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`ArtifactSaved`](#schema-artifactsaved) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-post-runs-run-id-artifacts-artifact-id-spreadsheet"></a>

### `POST /runs/{run_id}/artifacts/{artifact_id}/spreadsheet`

**Replace a table from a spreadsheet.**

Same rights as editing. A multipart `.xlsx` upload (`file`, `expected_version`); its rows become the artifact's new version.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |
| `artifact_id` | path | string | yes | An artifact id of the run's terminal spec, such as `kpis` |

**Request body** (`multipart/form-data`, required)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | file | yes |  |
| `expected_version` | integer | yes | ≥ 0 |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunChanged`](#schema-runchanged) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-post-runs-run-id-artifacts-artifact-id-attachments"></a>

### `POST /runs/{run_id}/artifacts/{artifact_id}/attachments`

**Attach a file to an artifact.**

Same rights as editing. A multipart upload (`file`, `expected_version`) of an allowed type (`ADLC_ATTACHMENT_TYPES`) and size (`ADLC_ATTACHMENT_MAX`), stored content-addressed with the artifact's current version. The file name is reduced to its last path segment.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |
| `artifact_id` | path | string | yes | An artifact id of the run's terminal spec, such as `kpis` |

**Request body** (`multipart/form-data`, required)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `file` | file | yes |  |
| `expected_version` | integer | yes | ≥ 0 |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunChanged`](#schema-runchanged) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-runs-run-id-artifacts-artifact-id-history"></a>

### `GET /runs/{run_id}/artifacts/{artifact_id}/history`

**An artifact's versions.**

Any signed-in person. Every version of the artifact on this run: who produced it, when, its hash, the version it was derived from, and its attachments.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |
| `artifact_id` | path | string | yes | An artifact id of the run's terminal spec, such as `kpis` |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | array of [`ArtifactHistoryEntry`](#schema-artifacthistoryentry) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-runs-run-id-attachments-content-hash"></a>

### `GET /runs/{run_id}/attachments/{content_hash}`

**Download an attachment.**

Any signed-in person. Only an attachment recorded on this run. Always a download: `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`, `Cache-Control: private, no-store`.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |
| `content_hash` | path | string | yes | The attachment's SHA-256, from the artifact's `attachments` |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | `application/octet-stream` | The file, as a download (Content-Disposition: attachment) |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

## Requests

Clarifications, waivers and dead-lettered events.

<a id="op-post-clarifications-clarification-id-answers"></a>

### `POST /clarifications/{clarification_id}/answers`

**Answer a clarification.**

A person in the role the agent addressed. One answer per question; the same run resumes (it does not count as rework). Answered once.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `clarification_id` | path | string | yes | A clarification: `<run id>/clar-<n>` (contains `/`) |

**Request body** (`application/json`, required)

[`Answers`](#schema-answers)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `answers` | array of string | yes | One answer per question, in order (at least 1 items; at most 50 items) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunSummary`](#schema-runsummary) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-post-waivers-waiver-id-decision"></a>

### `POST /waivers/{waiver_id}/decision`

**Approve or reject a waiver.**

A person in a role allowed to set the exception (or the terminal's accountable roles), and not the person who proposed it. Approval closes the run as an exception; rejection returns it to sign-off.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `waiver_id` | path | string | yes | A waiver, such as `WVR-0001` |

**Request body** (`application/json`, required)

[`WaiverDecision`](#schema-waiverdecision)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `approve` | boolean | yes | true approves the waiver, false rejects it |
| `comment` | string or null | no | Why (at most 4000 characters) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunSummary`](#schema-runsummary) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-dead-letters"></a>

### `GET /dead-letters`

**List dead-lettered events.**

The CoE role (`ADLC_DEADLETTER_ROLE`). Events the router could not deliver after its retries, with attempts, last error and how often each was re-queued.

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | array of [`DeadLetter`](#schema-deadletter) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |

<a id="op-get-dead-letters-event-id"></a>

### `GET /dead-letters/{event_id}`

**A dead letter's payload and history.**

The CoE role. The event's payload and its re-queue history.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `event_id` | path | string (uuid) | yes | The event's id (a dead letter's UUID, or a proposed event's id in its artifact) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`DeadLetterDetail`](#schema-deadletterdetail) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-post-dead-letters-event-id-requeue"></a>

### `POST /dead-letters/{event_id}/requeue`

**Re-queue a dead letter.**

The CoE role. Puts the event back in the outbox for delivery and records who did it.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `event_id` | path | string (uuid) | yes | The event's id (a dead letter's UUID, or a proposed event's id in its artifact) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 204 | none | Done; no body |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

## Changes

Change requests waiting for the ITSM approver (feature 012).

<a id="op-get-changes"></a>

### `GET /changes`

**Change requests waiting for a decision.**

The ITSM approver role named in the tool registry; empty for anyone else.

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | array of [`ChangeRequest`](#schema-changerequest) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |

<a id="op-post-changes-change-id-decision"></a>

### `POST /changes/{change_id}/decision`

**Approve or reject a change request.**

The ITSM approver role. Records the decision as a new version of the change record; runs whose controls wait for it re-run them.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `change_id` | path | string | yes | A change request, such as `CHG-1` |

**Request body** (`application/json`, required)

[`ChangeDecision`](#schema-changedecision)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `approve` | boolean | yes | true approves the change, false rejects it |
| `comment` | string or null | no | Why (at most 2000 characters) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`ChangeRequest`](#schema-changerequest) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

## Proposed events

Lifecycle events an agent proposed, waiting for a person (feature 012).

<a id="op-get-events-proposed"></a>

### `GET /events/proposed`

**Proposed events waiting for me.**

Events an agent proposed in a run's artifact, for a person in the terminal's accountable roles; empty for anyone else.

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | array of [`ProposedEvent`](#schema-proposedevent) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |

<a id="op-post-events-proposed-usecase-id-terminal-id-run-number-event-id"></a>

### `POST /events/proposed/{usecase_id}/{terminal_id}/{run_number}/{event_id}`

**Confirm or dismiss a proposed event.**

A person in the terminal's accountable roles. Confirming raises the event (and its route runs); dismissing records it. Each proposal is decided once. The run is named by its three parts (`UC-0001`, `T<n>`, `run-1`).

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `usecase_id` | path | string | yes | A use case, such as `UC-0001` |
| `terminal_id` | path | string | yes | A terminal id from the pinned specs, `T<n>` |
| `run_number` | path | string | yes | The run's last part, such as `run-1` |
| `event_id` | path | string | yes | The event's id (a dead letter's UUID, or a proposed event's id in its artifact) |

**Request body** (`application/json`, required)

[`EventDecision`](#schema-eventdecision)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `confirm` | boolean | yes | true raises the event, false dismisses it |
| `comment` | string or null | no | Why (at most 2000 characters) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`ProposedEventDecided`](#schema-proposedeventdecided) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 403 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_allowed`: the person may not do this (or a cookie session's change came without its CSRF value) |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 409 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `stale` (the run changed since the version sent) or `wrong_state` (not possible in the current state, or already decided) |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

## Dashboard

Read-only views over the platform's records (feature 013).

<a id="op-get-dashboard-usecases-usecase-id-journey"></a>

### `GET /dashboard/usecases/{usecase_id}/journey`

**A use case's journey view.**

Any signed-in person. Lanes per pinned terminal with a bar per run, arrows for reworks, reroutes, exceptions, events and re-entry with their causes, and the escalations and exceptions panel.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `usecase_id` | path | string | yes | A use case, such as `UC-0001` |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`Journey`](#schema-journey) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-dashboard-usecases-usecase-id-kpis"></a>

### `GET /dashboard/usecases/{usecase_id}/kpis`

**A use case's KPIs.**

Any signed-in person. Every KPI with its definition and value (`null` where it is not yet defined).

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `usecase_id` | path | string | yes | A use case, such as `UC-0001` |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`Kpis`](#schema-kpis) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-dashboard-portfolio"></a>

### `GET /dashboard/portfolio`

**KPIs across use cases.**

Any signed-in person. Counts and times summed, rates pooled; filter by `risk_tier` and `status`.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `risk_tier` | query | string or null | no | Only use cases of this risk tier |
| `status` | query | string or null | no | Only use cases in this status |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`Portfolio`](#schema-portfolio) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-dashboard-activity"></a>

### `GET /dashboard/activity`

**The activity feed.**

Any signed-in person. What agents, reviewers, people and the orchestrator did, newest first; filter by `usecase_id`, `terminal_id`, `actor_type` and `step`; `limit` 1 to 1000 (default 200).

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `usecase_id` | query | string or null | no | Only this use case |
| `terminal_id` | query | string or null | no | Only this terminal |
| `actor_type` | query | string or null | no | agent, reviewer, human, orchestrator or system |
| `step` | query | string or null | no | Only this run step |
| `limit` | query | integer | no | At most this many actions (1 to 1000) (default `200`) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | array of [`ActivityEntry`](#schema-activityentry) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

<a id="op-get-dashboard-runs-run-id-timeline"></a>

### `GET /dashboard/runs/{run_id}/timeline`

**A run's step timeline.**

Any signed-in person. Each step with its duration, and each agent attempt with its model and tool calls.

**Parameters**

| Name | In | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `run_id` | path | string | yes | A run, `<use case>/<terminal>/run-<n>`: `UC-0001/T<n>/run-2` (contains `/`) |

**Answers**

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | [`RunTimeline`](#schema-runtimeline) (`application/json`) | OK |
| 401 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_signed_in`: no session, or it expired or was revoked |
| 404 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `not_found`: no such use case, run, request, event or file |
| 422 | [`ErrorBody`](#schema-errorbody) (`application/json`) | `invalid`: the input was refused; `field` names it when one field is at fault |

## Schemas

The bodies the operations take and answer, in alphabetical order.

<a id="schema-activityentry"></a>

### `ActivityEntry`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `at` | string or null | yes |  |
| `usecase_id` | string | yes |  |
| `run_id` | string | yes |  |
| `terminal_id` | string | yes |  |
| `actor_type` | string | yes |  |
| `actor` | string | yes |  |
| `step` | string | yes |  |
| `outcome` | string or null | yes |  |
| `seconds` | number | yes |  |

<a id="schema-agentattempt"></a>

### `AgentAttempt`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | string | yes |  |
| `attempt` | integer | yes |  |
| `agent_id` | string | yes |  |
| `implementation` | string | yes |  |
| `steps` | integer or null | yes |  |
| `tokens_in` | integer or null | yes |  |
| `tokens_out` | integer or null | yes |  |
| `cost_usd` | number or null | yes |  |
| `model_calls` | array of [`Record`](#schema-record) | yes |  |
| `tool_calls` | array of [`Record`](#schema-record) | yes |  |

<a id="schema-answers"></a>

### `Answers`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `answers` | array of string | yes | One answer per question, in order (at least 1 items; at most 50 items) |

<a id="schema-approval"></a>

### `Approval`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `person` | string | yes |  |
| `role` | string | yes |  |
| `signed_at` | [`Timestamp`](#schema-timestamp) | yes |  |

<a id="schema-arrow"></a>

### `Arrow`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `from_run` | string | yes |  |
| `to_run` | string | yes |  |
| `kind` | string | yes |  |
| `event_type` | string | yes |  |
| `cause` | object | yes |  |
| `actor` | string or null | yes |  |
| `at` | string or null | yes |  |

<a id="schema-artifacthistoryentry"></a>

### `ArtifactHistoryEntry`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run_id` | string | yes |  |
| `artifact_id` | string | yes |  |
| `version` | integer | yes |  |
| `attempt` | integer or null | yes |  |
| `content_hash` | string | yes |  |
| `derived_from_version` | integer or null | yes |  |
| `producer_type` | string | yes |  |
| `producer_id` | string | yes |  |
| `schema_valid` | boolean | yes |  |
| `created_at` | [`Timestamp`](#schema-timestamp) | yes |  |
| `attachments` | array of [`Record`](#schema-record) | yes |  |

<a id="schema-artifactsaved"></a>

### `ArtifactSaved`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `changed` | boolean | yes |  |
| `run` | [`RunSummary`](#schema-runsummary) | yes |  |

<a id="schema-artifactversion"></a>

### `ArtifactVersion`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `version` | integer | yes |  |
| `producer_type` | string | yes |  |
| `producer_id` | string | yes |  |
| `schema_valid` | boolean | yes |  |
| `created_at` | [`Timestamp`](#schema-timestamp) | yes |  |

<a id="schema-browsersigninresponse"></a>

### `BrowserSignInResponse`

Cookie-mode sign-in: the token went into the HttpOnly cookie, not here.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `expires_at` | string (date-time) | yes |  |
| `person` | [`PersonOut`](#schema-personout) | yes |  |
| `csrf_token` | string | yes |  |

<a id="schema-changedecision"></a>

### `ChangeDecision`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `approve` | boolean | yes | true approves the change, false rejects it |
| `comment` | string or null | no | Why (at most 2000 characters) |

<a id="schema-changerequest"></a>

### `ChangeRequest`

A change request: the record's own fields (summary, window, risk, plan, state, and the decision once made) are the ITSM body, open by nature; the fields below are the platform's.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `change_id` | string | yes |  |
| `record_version` | integer | yes |  |
| `usecase_id` | string or null | yes |  |
| `run_id` | string or null | yes |  |
| `terminal_id` | string or null | yes |  |
| `at` | string | yes |  |
| *other keys* | any JSON | no | Kept as recorded |

<a id="schema-completion"></a>

### `Completion`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `artifacts` | object (string → array of object) | yes | Rows per artifact id, for the artifacts the agents could not finish |
| `expected_version` | integer | yes | The run version the person saw (≥ 0) |

<a id="schema-costtotals"></a>

### `CostTotals`

Model usage and cost (``adlc.agents.cost``).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `calls` | integer | yes |  |
| `tokens_in` | integer | yes |  |
| `tokens_out` | integer | yes |  |
| `cost_usd` | [`Money`](#schema-money) or null | yes |  |
| `unknown_cost_calls` | integer | yes |  |
| `fallback_answers` | integer | yes |  |

<a id="schema-deadletter"></a>

### `DeadLetter`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `event_id` | string (uuid) or string | yes |  |
| `event_type` | string | yes |  |
| `usecase_id` | string or null | yes |  |
| `causation_run_id` | string or null | yes |  |
| `attempts` | integer | yes |  |
| `last_error` | string or null | yes |  |
| `dead_lettered_at` | [`Timestamp`](#schema-timestamp) or null | yes |  |
| `requeues` | integer | yes |  |

<a id="schema-deadletterdetail"></a>

### `DeadLetterDetail`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `event_id` | string (uuid) or string | yes |  |
| `event_type` | string | yes |  |
| `usecase_id` | string or null | yes |  |
| `causation_run_id` | string or null | yes |  |
| `attempts` | integer | yes |  |
| `last_error` | string or null | yes |  |
| `dead_lettered_at` | [`Timestamp`](#schema-timestamp) or null | yes |  |
| `processed_at` | [`Timestamp`](#schema-timestamp) or null | yes |  |
| `payload` | any JSON | yes |  |
| `history` | array of [`Record`](#schema-record) | yes |  |

<a id="schema-decision"></a>

### `Decision`

A sign-off decision. Extra keys are refused, so a body cannot name another actor or role (FR-002): the decision is always the signed-in person's.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `decision` | `"pass"` or `"rework"` or `"exception"` or `"terminate"` | yes | The outcome; offered per person in the run detail's `form.outcomes` |
| `comment` | string or null | no | Why (rework and terminate) (at most 4000 characters) |
| `root_cause` | string or null | no | Rework only: one of `form.root_causes` (at most 100 characters) |
| `reason` | string or null | no | Needed when the decision differs from the reviewer's recommendation (at most 2000 characters) |
| `fields` | object | no | Values the outcome needs (`form.requires`, `form.typed_fields`, or `alternative` on pass) |
| `target_terminal` | string or null | no | Rework only, for causes in `form.target_terminal_for`: the owning terminal (at most 20 characters) |
| `expected_version` | integer | yes | The run version the person saw (≥ 0) |

<a id="schema-decisionform"></a>

### `DecisionForm`

What this person may decide and what each outcome needs (``adlc.inbox.forms``). Every value comes from the pinned spec and catalogues, so none is a literal here.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `outcomes` | array of string | yes | What this person may decide now |
| `requires` | object (string → array of string) | yes | Per outcome, the fields it needs |
| `root_causes` | array of string | yes | Rework root causes to choose from |
| `target_terminal_for` | array of string | yes | Root causes that also need `target_terminal` |
| `target_terminals` | array of string | yes | The use case's pinned terminals |
| `typed_fields` | array of string | yes | Values a pass or exception emits that the person types |
| `alternatives` | array of string | yes | Alternative routes a pass may take |
| `reason_required_unless` | string or null | yes | The reviewer's recommendation: any other decision needs a `reason` |
| `sign_off_role` | string or null | yes | The role this person signs under |
| `can_decide` | boolean | yes | May decide now (not while controls re-run or a waiver is pending) |
| `can_terminate` | boolean | yes | May terminate the run |
| `can_edit` | boolean | yes | May edit the artifacts |
| `can_complete_escalation` | boolean | yes | May complete the escalation |
| `controls_pending` | boolean | yes | Controls are re-running after an edit |
| `waiver_pending` | boolean | yes | A waiver awaits its approver |

<a id="schema-edit"></a>

### `Edit`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `rows` | any JSON | yes | The artifact's new rows (a table) or text |
| `expected_version` | integer | yes | The run version the person saw (≥ 0) |

<a id="schema-errorbody"></a>

### `ErrorBody`

Every refusal (``adlc.api.errors``): a kind the client can act on, the reason in words, and the field it concerns when the input was invalid. Never a stack trace.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | string | yes |  |
| `detail` | string | yes |  |
| `field` | string or null | no |  |

<a id="schema-eventdecision"></a>

### `EventDecision`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `confirm` | boolean | yes | true raises the event, false dismisses it |
| `comment` | string or null | no | Why (at most 2000 characters) |

<a id="schema-health"></a>

### `Health`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | `"ok"` or `"unavailable"` | yes |  |
| `checks` | object (string → `"ok"` or `"unavailable"`) | yes |  |

<a id="schema-inboxitem"></a>

### `InboxItem`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | string | yes | sign_off, clarification, escalation, waiver, blocked or dead_letter |
| `id` | string | yes | The run, clarification, waiver or event it is about |
| `usecase_id` | string or null | yes |  |
| `terminal_id` | string or null | yes |  |
| `run_id` | string or null | yes |  |
| `role` | string or null | yes | The person's role it is addressed to |
| `title` | string | yes | Platform words for the item |
| `arrived_at` | [`Timestamp`](#schema-timestamp) or null | yes |  |
| `due_at` | [`Timestamp`](#schema-timestamp) or null | yes |  |
| `controls_pending` | boolean | yes |  |

<a id="schema-journey"></a>

### `Journey`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `usecase` | [`JourneyUseCase`](#schema-journeyusecase) | yes |  |
| `lanes` | array of [`Lane`](#schema-lane) | yes |  |
| `arrows` | array of [`Arrow`](#schema-arrow) | yes |  |
| `panel` | [`Panel`](#schema-panel) | yes |  |
| `time_scale` | number | yes |  |

<a id="schema-journeyusecase"></a>

### `JourneyUseCase`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `usecase_id` | string | yes |  |
| `name` | string | yes |  |
| `risk_tier` | string or null | yes |  |
| `status` | string | yes |  |

<a id="schema-kpi"></a>

### `Kpi`

One KPI (``adlc.dashboard.kpis``); its value's form depends on the KPI (a number, a breakdown or nothing yet), and some KPIs add a per-terminal split, details or a note.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | yes |  |
| `name` | string | yes |  |
| `unit` | string | yes |  |
| `headline` | boolean | yes |  |
| `definition` | string | yes |  |
| `value` | any JSON | yes |  |
| `per_terminal` | any JSON | no |  |
| `detail` | any JSON | no |  |
| `definition_note` | string or null | no |  |

<a id="schema-kpis"></a>

### `Kpis`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kpis` | array of [`Kpi`](#schema-kpi) | yes |  |

<a id="schema-lane"></a>

### `Lane`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `terminal_id` | string | yes |  |
| `name` | string | yes |  |
| `runs` | array of [`LaneBar`](#schema-lanebar) | yes |  |

<a id="schema-lanebar"></a>

### `LaneBar`

A run in a lane, or several earlier runs collapsed into one bar (``collapsed`` set).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run_id` | string or null | yes |  |
| `terminal_id` | string | yes |  |
| `run_number` | integer | yes |  |
| `state` | string | yes |  |
| `final_status` | string or null | yes |  |
| `mode` | string or null | no |  |
| `opened_at` | string or null | yes |  |
| `closed_at` | string or null | yes |  |
| `seconds` | number | yes |  |
| `owner` | string or null | yes |  |
| `time_split` | object (string → number) | yes |  |
| `collapsed` | integer or null | no |  |

<a id="schema-meout"></a>

### `MeOut`

The signed-in person; with the session's CSRF value when the session is the cookie.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `account_name` | string | yes |  |
| `display_name` | string | yes |  |
| `roles` | array of string | yes |  |
| `csrf_token` | string or null | no |  |

<a id="schema-money"></a>

### `Money`

US dollars as a decimal string, such as "0.0125"

string.

<a id="schema-panel"></a>

### `Panel`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `escalations` | array of [`PanelEscalation`](#schema-panelescalation) | yes |  |
| `exceptions` | array of [`Record`](#schema-record) | yes |  |
| `unlinked` | array of [`PanelUnlinked`](#schema-panelunlinked) | yes |  |

<a id="schema-panelescalation"></a>

### `PanelEscalation`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run_id` | string | yes |  |
| `terminal_id` | string | yes |  |
| `trigger` | string or null | yes |  |

<a id="schema-panelunlinked"></a>

### `PanelUnlinked`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run_id` | string | yes |  |
| `event_type` | string | yes |  |

<a id="schema-personout"></a>

### `PersonOut`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `account_name` | string | yes |  |
| `display_name` | string | yes |  |
| `roles` | array of string | yes |  |

<a id="schema-portfolio"></a>

### `Portfolio`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `usecases` | integer | yes |  |
| `kpis` | array of [`Kpi`](#schema-kpi) | yes |  |

<a id="schema-priorrework"></a>

### `PriorRework`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run_id` | string | yes |  |
| `person` | string | yes |  |
| `signed_at` | [`Timestamp`](#schema-timestamp) | yes |  |
| `comment` | string or null | yes |  |
| `root_cause` | string or null | yes |  |

<a id="schema-proposedevent"></a>

### `ProposedEvent`

A proposal row of the run's artifact table (its values as the agent wrote them).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `event_id` | any JSON | yes |  |
| `event_type` | any JSON | yes |  |
| `raised_at` | any JSON | yes |  |
| `routed_to` | any JSON | yes |  |
| `run_id` | string | yes |  |
| `usecase_id` | string | yes |  |
| `terminal_id` | string | yes |  |

<a id="schema-proposedeventdecided"></a>

### `ProposedEventDecided`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `event_id` | string | yes |  |
| `event_type` | any JSON | yes |  |
| `confirmed` | boolean | yes |  |
| `by` | string | yes |  |
| `comment` | string | yes |  |
| `raised_event_id` | string or null | no |  |

<a id="schema-record"></a>

### `Record`

A record as the platform stored it (a sign-off, a clarification round, a waiver, a check, the reviewer's output…): its keys are the store's

An object with any keys.

<a id="schema-runartifact"></a>

### `RunArtifact`

One artifact of the terminal: its rows as stored (a table, text or nothing yet).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | yes |  |
| `columns` | array of string | yes |  |
| `condition` | any JSON | yes |  |
| `rows` | any JSON | yes |  |
| `version` | [`ArtifactVersion`](#schema-artifactversion) or null | yes |  |
| `attachments` | array of [`Record`](#schema-record) | yes |  |
| `citations` | array of [`Record`](#schema-record) | yes |  |

<a id="schema-runchanged"></a>

### `RunChanged`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run` | [`RunSummary`](#schema-runsummary) | yes |  |

<a id="schema-rundetail"></a>

### `RunDetail`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run` | [`RunSummary`](#schema-runsummary) | yes | The run at a glance |
| `spec` | [`SpecRef`](#schema-specref) | yes | The pinned terminal spec |
| `artifacts` | array of [`RunArtifact`](#schema-runartifact) | yes | Every artifact the spec declares |
| `prerequisites` | array of [`Record`](#schema-record) | yes | Each prerequisite with its latest result and reason |
| `control_results` | array of [`Record`](#schema-record) | yes | The controls' latest results |
| `recommendation` | [`Record`](#schema-record) or null | yes | The reviewer agent's recommendation, with its checklist `items` |
| `prior_rework` | array of [`PriorRework`](#schema-priorrework) | yes | Earlier runs of this terminal sent to rework, newest first |
| `clarifications` | array of [`Record`](#schema-record) | yes | Clarification rounds of this run |
| `approvals` | array of [`Approval`](#schema-approval) | yes | Passes recorded so far |
| `decisions` | array of [`Record`](#schema-record) | yes | Every sign-off decision on this run |
| `waiver` | [`Record`](#schema-record) or null | yes | The pending waiver, if any |
| `timer` | [`Timer`](#schema-timer) | yes | When the run is due, and whether it is overdue |
| `cost` | [`CostTotals`](#schema-costtotals) | yes | Model usage and cost of this run |
| `timeline` | array of [`Record`](#schema-record) | yes | The run's steps (`run_activity`) |
| `checks` | array of [`Record`](#schema-record) | yes | The policy engine's decisions |
| `checklist_results` | array of [`Record`](#schema-record) | yes | The checklist scores recorded |
| `ledger_record` | [`Record`](#schema-record) or null | yes | The evidence ledger record, once the run closed |
| `form` | [`DecisionForm`](#schema-decisionform) | yes | What this person may decide and what it needs |

<a id="schema-runsummary"></a>

### `RunSummary`

A run at a glance (``adlc.inbox.service.run_summary``); the answer of every run action.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run_id` | string | yes | `<use case>/<terminal>/run-<n>` |
| `usecase_id` | string | yes |  |
| `terminal_id` | string | yes |  |
| `run_number` | integer | yes |  |
| `state` | string | yes | The run state (opened, building, awaiting_sign_off, …) |
| `final_status` | string or null | yes | The outcome once closed (pass, rework…) |
| `version` | integer | yes | Send it back as `expected_version` when acting |
| `controls_pending` | boolean | yes | Controls are re-running after an edit |
| `opened_at` | [`Timestamp`](#schema-timestamp) | yes |  |
| `closed_at` | [`Timestamp`](#schema-timestamp) or null | yes |  |
| `due_at` | [`Timestamp`](#schema-timestamp) or null | yes | When the current wait is due |

<a id="schema-runtimeline"></a>

### `RunTimeline`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `run_id` | string | yes |  |
| `activity` | array of [`TimelineActivity`](#schema-timelineactivity) | yes |  |
| `attempts` | array of [`AgentAttempt`](#schema-agentattempt) | yes |  |

<a id="schema-signinrequest"></a>

### `SignInRequest`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `account_name` | string | yes | at least 1 characters; at most 40 characters |
| `password` | string (password) | yes | at least 1 characters |
| `session` | `"bearer"` or `"cookie"` | no | `bearer`: answer a token. `cookie` (the browser): set the HttpOnly session cookie; needs the header `X-ADLC-CSRF: sign-in` (default `bearer`) |

<a id="schema-signinresponse"></a>

### `SignInResponse`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `token` | string | yes |  |
| `token_type` | `"bearer"` | no | default `bearer` |
| `expires_at` | string (date-time) | yes |  |
| `person` | [`PersonOut`](#schema-personout) | yes |  |

<a id="schema-specref"></a>

### `SpecRef`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `terminal_id` | string | yes |  |
| `version` | string | yes |  |

<a id="schema-submission"></a>

### `Submission`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | A short name (at least 1 characters; at most 200 characters) |
| `intake_text` | string | yes | The problem, the people involved and the outcome wanted, in the submitter's words (at least 1 characters; at most 20000 characters) |

<a id="schema-submitted"></a>

### `Submitted`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `usecase_id` | string | yes |  |

<a id="schema-terminalsummary"></a>

### `TerminalSummary`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `terminal_id` | string | yes |  |
| `runs` | integer | yes |  |
| `reworks` | integer | yes |  |
| `clarification_rounds` | integer | yes |  |
| `escalations` | integer | yes |  |
| `automatic_seconds` | number | yes |  |
| `waiting_seconds` | number | yes |  |

<a id="schema-timelineactivity"></a>

### `TimelineActivity`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `at` | string or null | yes |  |
| `step` | string | yes |  |
| `actor_type` | string | yes |  |
| `actor` | string | yes |  |
| `outcome` | string or null | yes |  |
| `seconds` | number | yes |  |

<a id="schema-timer"></a>

### `Timer`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `due_at` | [`Timestamp`](#schema-timestamp) or null | yes |  |
| `overdue` | boolean | yes |  |

<a id="schema-timestamp"></a>

### `Timestamp`

A time, ISO 8601 in UTC

string (date-time) or string.

<a id="schema-usecase"></a>

### `UseCase`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `usecase_id` | string | yes |  |
| `name` | string | yes |  |
| `intake_text` | string | yes |  |
| `submitted_by` | string | yes |  |
| `risk_tier` | string or null | yes |  |
| `status` | string | yes |  |

<a id="schema-usecasecost"></a>

### `UseCaseCost`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `total` | [`CostTotals`](#schema-costtotals) | yes |  |
| `terminals` | object (string → [`CostTotals`](#schema-costtotals)) | yes |  |

<a id="schema-usecasejourney"></a>

### `UseCaseJourney`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `usecase` | [`UseCase`](#schema-usecase) | yes |  |
| `runs` | array of [`RunSummary`](#schema-runsummary) | yes |  |
| `summary` | array of [`TerminalSummary`](#schema-terminalsummary) | yes |  |
| `cost` | [`UseCaseCost`](#schema-usecasecost) | yes |  |

<a id="schema-usecaselistitem"></a>

### `UseCaseListItem`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `usecase_id` | string | yes |  |
| `name` | string | yes |  |
| `submitted_by` | string | yes |  |
| `risk_tier` | string or null | yes |  |
| `status` | string | yes |  |
| `submitted_at` | [`Timestamp`](#schema-timestamp) | yes |  |
| `open_runs` | integer | yes |  |

<a id="schema-verification"></a>

### `Verification`

A hash-chain verification (``adlc.ledger.verify.Report``).

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `scope` | string | yes |  |
| `records_checked` | integer | yes |  |
| `verified` | boolean | yes |  |
| `breaks` | array of object | yes |  |
| `unscoped` | array of string | yes |  |

<a id="schema-waiverdecision"></a>

### `WaiverDecision`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `approve` | boolean | yes | true approves the waiver, false rejects it |
| `comment` | string or null | no | Why (at most 4000 characters) |
