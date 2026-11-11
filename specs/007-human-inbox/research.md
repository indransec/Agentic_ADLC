# Research: Human Inbox

## R-01 Two processes: the API is the only boundary

**Decision**:
- **API:** the platform API (FastAPI, feature 001) gains the operations of this feature. It runs
  them through the existing services:
  - `OrchestratorService` (feature 003);
  - `LedgerService` (feature 005);
  - the cost readers (feature 006);
  - a new `InboxService`.
- **UI:** the web application is a separate Streamlit process (container `ui`). It calls the API
  over HTTP with the person's bearer token, kept in the Streamlit session state on the server,
  never in the browser.
- **No database access from the UI:** the UI never opens a database connection (FR-020).

**Rationale**:
- SA §8: one approval API serves every channel, so Teams and ServiceNow can be added later.
- Authorization lives in one place.
- The UI cannot bypass role checks.

**Alternatives**: Streamlit calling the services in-process. That would bypass the API, and the
UI would need database credentials.

## R-02 The API process builds the services it needs

**Decision**: `create_app` builds, once:
- `PostgresTerminalRun` with the real policy engine (`build_policy_engine`, same settings as the
  orchestrator: synthetic data folder, account directory);
- `OrchestratorService(deadletter_role)`;
- `LedgerService` with the file store.

It gets stub agent and stub reviewer objects, because the API never advances runs. The
orchestrator worker does that.

The API needs the real policy engine because a decision computes the required conditional
approvers (`plus` conditions) and re-runs controls after an edit. Both evaluate expressions.

**Settings**:
- `deadletter_role`, `synthetic_dir` and `spec_dir` move from `OrchestratorSettings` to
  `RuntimeSettings`, so the API reads the same values.
- Compose passes them to the API container, which already mounts the file store volume.

## R-03 The inbox is derived from the run tables, not stored

**Decision**: `InboxService.items(person)` computes the items on each request. There is no
inbox table.

| Kind | Source |
| --- | --- |
| sign-off | Runs in `awaiting_sign_off`. For each, `runs.context(conn, run)` gives the rule roles, required conditional roles and approvals. Shown when the person holds one of the still-needed roles and has not approved. Marked `controls_pending` when an edit's re-check is running. |
| clarification | Unanswered rounds whose `addressed_role` the person holds |
| escalation | Runs in `escalated` whose terminal's accountable roles the person holds |
| waiver | Runs with a pending waiver whose approver roles the person holds, where the person is not the proposer. The approvers are the spec's `exception` set-by roles, else the accountable roles (the 003 rule). |
| blocked | Runs in `blocked` whose terminal's accountable roles the person holds (change request 2026-11-11) |
| dead letter | Dead-lettered events, for the CoE role only |

Each item has kind, use case, terminal, run, role, title, arrival time and due time.

**Rationale**:
- One source of truth; nothing to keep in sync.
- MVP volume is small: tens of open runs.
- The rules reuse the services' own role logic. A shared `can_*` function per action is used by
  both the inbox and the operation, so the two never disagree.

## R-04 Run detail and the decision form come from the spec

**Decision**: `GET /runs/{run_id}` returns one document:
- the run (state, version, `controls_pending`, timer);
- the artifacts, from feature 005's current versions, with attachments;
- the artifact declarations: columns and conditions;
- control results;
- the recommendation (status, reason, root cause, scores with the checklist item text, findings);
- prior rework comments (sign-off comments of this terminal's earlier runs that closed as rework);
- clarifications;
- approvals so far;
- the activity timeline and checks (feature 005 `run_view`);
- cost (feature 006 `run_cost`);
- `form`, built from the pinned spec:
  - outcomes allowed for people (`status_rights.human`);
  - required fields per outcome (`outcome.requires`);
  - root causes (`outcome_model.rework.route_by_root_cause` keys);
  - emitted values a person must type;
  - whether the person may decide and may edit.

**Rationale**: FR-008, FR-009 and FR-022. The UI renders the form from data, with no terminal
logic.

## R-05 Errors and optimistic concurrency

**Decision**: one error body, `{"kind": ..., "detail": ...}`, mapped from the service exceptions:

| Exception | HTTP | `kind` |
| --- | --- | --- |
| (no session) | 401 | `not_signed_in` (feature 001 middleware) |
| `NotAuthorised` | 403 | `not_allowed` |
| `UnknownRun`, unknown use case, waiver, clarification or file | 404 | `not_found` |
| `StaleRun` | 409 | `stale` |
| `InvalidTransition`, `AlreadyAnswered` | 409 | `wrong_state` |
| `InvalidDecision`, `InvalidUpload`, `AttachmentRefused`, `UnknownArtifact`, validation errors | 422 | `invalid` (with the field where known) |

Decisions, edits, uploads, attachments and escalation completion carry `expected_version`.
`LedgerService.edit_artifact` and `OrchestratorService.complete_escalation` gain an optional
`expected_version`, an additive change.

## R-06 Downloads are served safely

**Decision**: `GET /runs/{run_id}/attachments/{content_hash}` answers only for attachments of
that run. It returns the bytes with:

- `Content-Type`: the recorded media type;
- `Content-Disposition: attachment; filename*=UTF-8''<name>`;
- `X-Content-Type-Options: nosniff`;
- `Content-Security-Policy: default-src 'none'; sandbox`;
- `Cache-Control: private, no-store`.

The UI offers it through a download button and never renders it.

## R-07 Text from agents and people is shown as text

**Decision**:
- The UI never passes agent or person text to Markdown or HTML rendering. Free text (comments,
  findings, intake, clarification answers) goes through `st.text` or `st.code`.
- Tables go through `st.dataframe` and `st.data_editor`, which render cells as text.
- Labels the platform writes itself may use Markdown.
- A test sends `<script>` and Markdown link payloads through every free-text field. It then checks
  the rendered elements of the script tests: no Markdown or HTML element carries the payload.

## R-08 Streamlit pinned; tests use AppTest over the real API

**Decision**:
- **Pin:** `streamlit==1.66.1` (Apache-2.0, released 2026-10-21, at least two weeks old).
  `httpx` moves from the dev dependencies to the main ones (BSD-3, the UI's HTTP client).
  `python-multipart` (Apache-2.0) is added for the API's file uploads.
- **Tests:** UI tests use `streamlit.testing.v1.AppTest`. The API client is injected into the
  session state, backed by `httpx` with an ASGI transport to the real FastAPI app on the test
  database. The UI is therefore exercised end to end through the API, with no browser and no
  network.
- **API tests:** API tests use FastAPI's test client over the same harness, the stub agents and
  the stub reviewer.

## R-09 The UI process and its settings

**Decision**:
- **Container:** container `ui`, using the same image, runs
  `streamlit run src/adlc/ui/app.py --server.port 8501 --server.address 0.0.0.0
  --server.headless true --browser.gatherUsageStats false`.
- **Settings:** `ADLC_API_URL` (default `http://api:8000`) and `ADLC_UI_PORT` (host port, default
  8501).
- **Pages:** sign-in, inbox, intake, use cases and journey, run detail, and dead letters (CoE).
- **Inbox refresh:** a 30-second auto-refresh, plus a manual refresh button (FR-007).
- **Streamlit protections:** XSRF protection stays on, the default. CORS is not needed, because
  the UI calls the API from the server.

## R-10 Tracing and records

**Decision**:
- **Tracing:** FastAPI is already instrumented (feature 001). Each operation adds the span
  attributes `account`, `run_id` and `usecase_id`.
- **Records:** every human action already writes its run activity and sign-off rows through the
  services (SA §8.2). The API adds no other records.
- **Logging:** the API logs no request bodies, because they may hold artifact content.

## R-11 Gate 2 defaults (approved 2026-11-11)

- **Prior rework comments:** every earlier run of this terminal in this use case that closed as
  rework, newest first, each with who, when, comment and root cause.
- **Large tables:** artifact tables are editable up to 1,000 rows, with scrolling. Above that the
  table is read-only, and spreadsheet upload is offered instead.
- **Inbox order:** soonest due first, then by arrival. Items without a due time come last.
- **Sign-out:** sign-out, or an expired session, clears the token from the UI session and returns
  to sign-in. Nothing else is kept.
- **UI port:** the default is 8501, changed with `ADLC_UI_PORT`.
