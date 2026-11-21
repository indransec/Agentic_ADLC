# Contract: API, commands, settings and process

## Platform API (session required; CoE = the role in `ADLC_DEADLETTER_ROLE`)

| Method and path | Who | Does |
| --- | --- | --- |
| `GET /board/health` | CoE | sync health (FR-022): `enabled`, `mapping_ok`, `last_poll_at`, `last_poll_outcome`, `watermark`, `watermark_age_s`, `outbound_pending`, `outbound_oldest_age_s`, `dead_lettered` (use case ids), `refused_by_reason`, `reverted_count`, `last_reconciliation` (`id`, `at`, `differences`) |
| `POST /board/reconciliations` | CoE | run a reconciliation now (FR-019); returns its report |
| `GET /board/reconciliations/{id}` | CoE | a past report |
| `POST /board/requeue/{usecase_id}` | CoE | requeue a dead-lettered use case's projection |

Others get `403`. The API process never polls; reconciliation runs in the request (bounded by
SC-006, under 1 minute for 50 use cases).

## Commands (`adlc-board`, a new script in `pyproject.toml`)

| Command | Does | Exit |
| --- | --- | --- |
| `adlc-board run` | the sync process: check the mapping, then poll and project forever; `/health` on `ADLC_BOARD_PORT` | — |
| `adlc-board check-mapping` | the board check of the mapping (R-12) | 0 ok, 1 gaps (listed), 2 settings |
| `adlc-board reconcile --as <account>` | reconciliation; the account must hold the CoE role | 0, 1 refused or failed |
| `adlc-board health` | print sync health | 0 |
| `adlc-board requeue <usecase_id> --as <account>` | requeue a dead letter | 0, 1 |

## Settings (prefix `ADLC_`)

| Name | Default | Notes |
| --- | --- | --- |
| `ADLC_BOARD_ENABLED` | `false` | when false, `adlc-board run` reports `disabled` and does nothing |
| `ADLC_BOARD_URL` | — | e.g. `http://ado-sim:8600` (compose), `http://127.0.0.1:8600` (local) |
| `ADLC_BOARD_IDENTITIES_URL` | `ADLC_BOARD_URL` | `https://vssps.dev.azure.com` for real ADO |
| `ADLC_BOARD_ORGANIZATION` | — | `adlc-demo` |
| `ADLC_BOARD_PROJECT` | — | `Agentic ADLC` |
| `ADLC_BOARD_TOKEN` | — | secret, at least 20 characters; the service account's token |
| `ADLC_BOARD_SERVICE_IDENTITY` | — | the service account's unique name |
| `ADLC_BOARD_EVIDENCE_URL` | — | base of the run evidence link, e.g. `http://127.0.0.1:8501/run?id=` |
| `ADLC_BOARD_MAPPING_FILE` | `adlc-specs/tracker_mapping.yaml` | |
| `ADLC_BOARD_START_FROM` | unset | first watermark on first start; unset = the board's latest change (history is not replayed, FR-010a) |
| `ADLC_BOARD_PORT` | `8050` | the process's `/health` |

Required only when `ADLC_BOARD_ENABLED=true` (validated at start; the message names each).

## Process

- Compose service `board` (platform image, `adlc-board run`, platform network, healthcheck on
  `/health`, `depends_on` `migrate` and `ado-sim`); `deploy/Procfile.local` process `board`;
  `deploy/local.env` sets `ADLC_BOARD_URL=http://127.0.0.1:8600`.
- Turning it on for the demo: issue the service account's token in the simulator, put it in
  `ADLC_BOARD_TOKEN`, set `ADLC_BOARD_ENABLED=true`, add `board_identity` to each demo account.
