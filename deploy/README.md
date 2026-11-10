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
