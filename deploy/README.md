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

## Knowledge MCP server (feature 008)

The `knowledge` service is the read-only grounding of the T0–T2 agents. It serves one MCP endpoint
per enterprise source (`/mcp/confluence`, `/mcp/sharepoint`, `/mcp/portfolio`, `/mcp/jira`,
`/mcp/arch_repo`, `/mcp/mcp_registry`) over the synthetic document set in `data/knowledge`, which
is part of the image. It is reachable only inside the Compose network.

- Set `ADLC_KNOWLEDGE_TOKEN` in `.env` to a random secret of at least 16 characters. The server
  and the orchestrator share it; compose refuses to start without it.
- Health: `GET /health` inside the network.
- To use your own documents, mount a folder and point `ADLC_KNOWLEDGE_DIR` at it (format in
  `data/knowledge/README.md`).
