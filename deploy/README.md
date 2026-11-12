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

## MCP tool servers (feature 010)

- `tools`: the eval store and the enterprise mocks (ITSM, CMDB, agent registry, IAM, GRC, control
  library), platform network, app database role.
- `pilot-bridge`: the pilot-facing servers (environments, Git, CI, artifact store, prompt registry,
  datasets, harness, red-team, personal-data scan, deploy, traffic, kill switch, observability,
  monitors, feedback). The only service on both networks; it holds no database, model, knowledge or
  session settings.
- `pilot-lab` (pilot image, pilot network): builds and datasets for CI and the harness.

Set `ADLC_TOOLS_TOKEN_KEY` (at least 32 characters, generated locally, never committed): the
platform signs a five-minute run token per tool call with it and both servers verify it. Without
it the orchestrator starts with no acting tools and reads synthetic `env`/`template` evidence
(labelled). Call any tool by hand with the probe, inside the platform network:

```bash
docker compose -f deploy/compose.yaml --env-file .env run --rm -T orchestrator \
  adlc-tools-probe --usecase <use case> --terminal <terminal id> <tool> --arg key=value
```

Only a person releases the prod-sim kill switch: `pt pilot-kill release --reason <text>`.

## Pilot environments (feature 009)

The pilot, an Incident Triage Assistant, runs on its own network (`adlc-pilot`) in the
`adlc-pilot:0.1.0` image: `pilot-dev`, `pilot-test` and `pilot-prodsim` (environment hosts) and
`pilot-traffic`. It publishes no ports and mounts no Docker socket. Only Jaeger, and later feature
010's MCP servers, join both networks.

```bash
pt() { docker compose -f deploy/compose.yaml --env-file .env run --rm pilot-tools "$@"; }   # bash or zsh
pt pilot-build --fill fills/default            # prints the package hash
pt pilot-env pilot-dev create --package <hash>
pt pilot-split full --stable <hash>            # prod-sim; canary: --candidate <hash> --share 0.2
pt pilot-traffic-ctl rate 5 && pt pilot-traffic-ctl start
pt pilot-fault model_swap trigger              # and revert; pii_leak likewise
deploy/pilot-isolation-check.sh                # both directions closed (SC-007)
```

Pilot settings use the `PILOT_` prefix (see `.env.example`); `PILOT_MODEL_API_KEY` is only for the
optional real model in dev and test, and is empty by default.
