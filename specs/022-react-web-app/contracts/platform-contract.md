# Contract: Typed answers and generated types

Research R-04 and R-05.

## Routes that gain a response model

| Router | Route | Model module |
| --- | --- | --- |
| artifacts | `PUT /runs/{run_id}/artifacts/{artifact_id}` | `schemas/artifacts.py` |
| artifacts | `POST /runs/{run_id}/artifacts/{artifact_id}/spreadsheet` | `schemas/artifacts.py` |
| artifacts | `POST /runs/{run_id}/artifacts/{artifact_id}/attachments` | `schemas/artifacts.py` |
| artifacts | `GET /runs/{run_id}/artifacts/{artifact_id}/history` | `schemas/artifacts.py` |
| changes | `GET /changes` | `schemas/changes.py` |
| changes | `POST /changes/{change_id}/decision` | `schemas/changes.py` |
| dashboard | `GET /dashboard/usecases/{usecase_id}/journey` | `schemas/dashboard.py` |
| dashboard | `GET /dashboard/usecases/{usecase_id}/kpis` | `schemas/dashboard.py` |
| dashboard | `GET /dashboard/portfolio` | `schemas/dashboard.py` |
| dashboard | `GET /dashboard/activity` | `schemas/dashboard.py` |
| dashboard | `GET /dashboard/runs/{run_id}/timeline` | `schemas/dashboard.py` |
| events | `GET /events/proposed` | `schemas/events.py` |
| events | `POST /events/proposed/{usecase_id}/{terminal_id}/{run_number}/{event_id}` | `schemas/events.py` |
| inbox | `GET /inbox` | `schemas/inbox.py` |
| requests | `POST /clarifications/{clarification_id}/answers` | `schemas/requests.py` |
| requests | `POST /waivers/{waiver_id}/decision` | `schemas/requests.py` |
| requests | `GET /dead-letters` | `schemas/requests.py` |
| requests | `GET /dead-letters/{event_id}` | `schemas/requests.py` |
| runs | `POST /runs/{run_id}/decisions` | `schemas/runs.py` |
| runs | `POST /runs/{run_id}/escalation` | `schemas/runs.py` |
| runs | `GET /runs/{run_id}` (run detail, including `form`) | `schemas/runs.py` |
| usecases | `POST /usecases` | `schemas/usecases.py` |
| usecases | `GET /usecases` | `schemas/usecases.py` |
| usecases | `POST /usecases/{usecase_id}/verify` | `schemas/usecases.py` |
| usecases | `GET /usecases/{usecase_id}` | `schemas/usecases.py` |

Not changed:
- **Already typed:** `/auth/*` (extended in session.md) and `/health`.
- **Raw responses that stay raw:** attachment download (bytes with `Content-Disposition:
  attachment`), sign-out, and dead-letter re-queue (both 204). Their answers are documented with
  `responses=` so the OpenAPI document is complete.

## Rules

- Every model derives from `adlc.api.schemas.base.ApiModel` (`extra="forbid"`). Field names are
  exactly today's keys, so the JSON does not change.
- Open-ended content (artifact rows and cells, event payloads, control result details) is
  `JsonValue`, never `Any`.
- Enumerations that come from specs or catalogues (outcomes, root causes, terminal ids, roles,
  states) are `str`, not literals, so nothing terminal-specific enters code (constitution I).
- **Golden test.** `tests/integration/api/test_response_shapes.py` records every route's JSON on
  the scripted harness walk before the models go in, and must pass unchanged after.

## Generation

```text
make openapi
  uv run python -m scripts.export_openapi  -> web/src/api/openapi.json  (sorted keys, 2-space indent)
  pnpm -C web exec openapi-typescript src/api/openapi.json -o src/api/schema.d.ts
```

**Freshness.**
- **Python side:** `tests/unit/api/test_openapi_fresh.py` compares the live schema with the
  committed JSON. It runs in `make test`, no Node needed.
- **Web side:** `web-typecheck` regenerates `schema.d.ts` into a temporary file and diffs it with
  the committed one.

Either mismatch fails `make check` (FR-021, SC-008).
