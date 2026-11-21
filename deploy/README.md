# Deployment notes

`compose.yaml` runs the demo host: Phoenix (traces), the one-shot `migrate` and `register` services, the
API and the orchestrator. The platform database is one SQLite file on the `adlc-db` volume
(`/var/lib/adlc/db/adlc.db`), shared by `migrate`, `register`, `api`, `orchestrator` and `tools`;
SQLite allows one writer at a time and the file must stay on this host's local disk.
To run the same processes without Docker, see `docs/run-without-docker.md` (`make local`).

## Backups

Back up two things together, at the same point in time:

- the database volume (`adlc-db`); copy the file with `sqlite3 adlc.db ".backup ..."` or stop the
  services first, so the copy is consistent;
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
  library), platform network, the platform database.
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
`pilot-traffic`. It publishes no ports and mounts no Docker socket. Only Phoenix (the trace
collector), and feature 010's pilot bridge, join both networks.

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

## ADO simulator (feature 015)

The `ado-sim` service (`ado_sim/`, its own locked uv project, image `adlc-ado-sim:0.1.0` from
`deploy/ado-sim.Dockerfile`) serves the Azure DevOps REST API 7.1 subset the tracker adapter
(feature 016) uses, on the platform network as `http://ado-sim:8600` and on the host at
`ADO_SIM_PORT` (default 8600). Its data is one SQLite file on the `ado-sim-data` volume. On every
start the image migrates, seeds from `seed/demo.yaml` only when the database is new, then serves;
it runs as a non-root user. `ADO_SIM_TOKEN_KEY` (at least 32 characters, in `.env`) is required:
it signs the personal access tokens, and changing it invalidates them all. Traces go to Phoenix,
project `ado-sim`.

```bash
sim() { docker compose -f deploy/compose.yaml --env-file .env exec ado-sim ado-sim "$@"; }   # bash or zsh
sim token issue adlc-platform@adlc.demo        # printed once; store it where the client reads it
sim token list                                 # ids, identities, labels; never the tokens
sim token revoke <id>
sim reset --yes                                # remove all simulator data and seed again
sim password set --all                         # page passwords for every demo user (017); asked twice
```

The board page is at `http://localhost:${ADO_SIM_PORT:-8600}/`: sign in as a demo user with the
page password (or a personal access token). `ADO_SIM_DEMO_PASSWORD` in `.env` turns on a shared
demo password for rehearsals; leave it empty for the demo.

Removing the `ado-sim-data` volume (`make reset` removes every volume) loses the simulator's work
items and tokens; the next start seeds a fresh board. Known differences from real ADO are listed
in `ado_sim/contract/differences.md`.

## Board engagement (feature 016)

The `board` service (platform image, `adlc-board run`) keeps the board (the `ado-sim` service) and
the platform in step: it projects use cases, runs and clarifications onto the board, and turns
people's board changes (decisions, answers, new Epics) into platform requests, applied with the
same checks as the inbox. It is **off** until `ADLC_BOARD_ENABLED=true`; off, it only answers
`/health` (`disabled`), so `make up --wait` is unaffected. Its state is in the platform database
(tables `board_*` and `inbound_*`), so the `adlc-db` backup covers it.

Turning it on for the demo:

```bash
sim() { docker compose -f deploy/compose.yaml --env-file .env exec ado-sim ado-sim "$@"; }
sim token issue adlc-platform@adlc.demo      # the service account's token
# .env: ADLC_BOARD_ENABLED=true and ADLC_BOARD_TOKEN=<that token>
# accounts file: board_identity: <user>@adlc.demo on each account that acts on the board
#   (the simulator's seeded users, e.g. product.owner@adlc.demo)
make up
docker compose -f deploy/compose.yaml --env-file .env exec board adlc-board check-mapping
```

The defaults point at the simulator (`ADLC_BOARD_URL=http://ado-sim:8600`, organisation
`adlc-demo`, project `Agentic ADLC`, service identity `adlc-platform@adlc.demo`); see
`.env.example`. The `board` and `api` services read the same board settings (`x-board-settings`):
the API answers the web app's mode, links to board items and runs reconciliation. With the sync
on, the web app is the operations console and people decide on the board (feature 019); a link
from the console to a work item uses `ADLC_BOARD_PUBLIC_URL` (default `http://localhost:8600`,
the address a browser on the host reaches). To fall back to the inbox, set
`ADLC_BOARD_ENABLED=false` and `make up` again. The CoE (`ADLC_DEADLETTER_ROLE`) reads sync health and reconciles:

```bash
board() { docker compose -f deploy/compose.yaml --env-file .env exec board adlc-board "$@"; }
board health                                 # watermark age, pending deliveries, refusals
board reconcile --as <coe account>           # make the board match the platform; prints the report
board requeue UC-0001 --as <coe account>     # a dead-lettered projection
```

The same are served by the API: `GET /board/health`, `POST /board/reconciliations`,
`GET /board/reconciliations/{id}`, `POST /board/requeue/{usecase_id}` (CoE only).

## Traces (Arize Phoenix)

The `phoenix` service (`deploy/phoenix`, its own locked uv project, image `adlc-phoenix:0.1.0`)
receives OTLP over HTTP on `:6006/v1/traces` and serves the UI and REST API on the same port
(`ADLC_PHOENIX_UI_PORT`). Its data is a SQLite file on the `phoenix-data` volume. Projects come
from `OTEL_RESOURCE_ATTRIBUTES` (`openinference.project.name`): `adlc-platform` for the API and the
orchestrator, `pilot-triage-<environment>` for each pilot host; the pilot bridge reads
`pilot-triage-prod-sim` through `ADLC_BRIDGE_PHOENIX_URL`. A stopped Phoenix never fails a request:
exports are batched and their failures logged.

