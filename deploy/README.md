# Deployment notes

`compose.yaml` runs the demo host: Postgres, Jaeger, the one-shot `migrate` and `register`
services, the API and the orchestrator.

## Backups

Back up two things together, at the same point in time:

- the Postgres data volume (`adlc-pgdata`);
- the evidence file store volume (`adlc-files`), mounted at `/var/lib/adlc/files`.

The ledger records the content hash of every attached file (feature 005), so a file store
restored from a different point in time than the database shows up as `attachment` breaks in
`adlc-ledger verify`.

## Web application (feature 007)

The `ui` service runs the Streamlit web application on `${ADLC_UI_PORT:-8501}`. It talks only to
the `api` service (`ADLC_API_URL`) and holds no database settings or secrets. The API runs every
human operation, so it now also needs `ADLC_DEADLETTER_ROLE`, `ADLC_SYNTHETIC_DIR` and
`ADLC_SPEC_DIR`, the same values as the orchestrator.
