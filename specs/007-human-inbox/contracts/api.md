# Contract: Platform API Operations (feature 007)

All operations need `Authorization: Bearer <token>` (feature 001); `/health` and `/auth/sign-in`
stay public. Bodies are JSON unless marked multipart. Errors: `{"kind", "detail", "field"?}` with
the statuses of research R-05.

## Use cases

| Method and path | Body | Answer | Rules |
| --- | --- | --- | --- |
| `POST /usecases` | `{name (1–200), intake_text (1–20000)}` | `201 {usecase_id}` | Feature 003 submit rules |
| `GET /usecases?mine=true\|false` | — | `[{usecase_id, name, submitted_by, submitted_at, risk_tier, open_runs}]` | `mine`: submitted by the person, or holding a role in one of its terminals |
| `GET /usecases/{usecase_id}` | — | `{usecase, runs:[{run_id, terminal_id, run_number, state, final_status, opened_at, closed_at, due_at}], summary:[...] (005), cost:{...} (006)}` | Any signed-in person |
| `POST /usecases/{usecase_id}/verify` | — | Feature 005 report | Any signed-in person; recorded under the account |

## Inbox

| Method and path | Answer |
| --- | --- |
| `GET /inbox` | `[{kind: sign_off\|clarification\|escalation\|waiver\|dead_letter, id, usecase_id, terminal_id, run_id, role, title, arrived_at, due_at, controls_pending}]`, newest due first |

## Runs

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /runs/{run_id}` | — | Run detail (research R-04) |
| `POST /runs/{run_id}/decisions` | `{decision, comment?, root_cause?, reason?, fields?, target_terminal?, expected_version}` | `200` run summary |
| `POST /runs/{run_id}/escalation` | `{artifacts: {id: rows}, expected_version}` | `200` run summary |

## Artifacts and files

| Method and path | Body | Answer |
| --- | --- | --- |
| `PUT /runs/{run_id}/artifacts/{artifact_id}` | `{rows, expected_version}` | `200 {changed: bool, run}` |
| `POST /runs/{run_id}/artifacts/{artifact_id}/spreadsheet` | multipart `file`, `expected_version` | `200 {run}` |
| `POST /runs/{run_id}/artifacts/{artifact_id}/attachments` | multipart `file`, `expected_version` | `200 {run}` |
| `GET /runs/{run_id}/artifacts/{artifact_id}/history` | — | Feature 005 history |
| `GET /runs/{run_id}/attachments/{content_hash}` | — | The bytes, with the download headers of research R-06 |

## Clarifications, waivers, dead letters

| Method and path | Body | Answer |
| --- | --- | --- |
| `POST /clarifications/{clarification_id}/answers` | `{answers: [str, ...]}` | `200` run summary |
| `POST /waivers/{waiver_id}/decision` | `{approve: bool, comment}` | `200` run summary |
| `GET /dead-letters` | — | Feature 003 list (CoE role only) |
| `POST /dead-letters/{event_id}/requeue` | — | `204` (CoE role only) |

## Run summary (the answer to actions)

`{run_id, usecase_id, terminal_id, state, final_status, version, controls_pending}`
