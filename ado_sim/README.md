# ADO simulator

A stand-in for Azure DevOps Boards: the subset of the Azure DevOps REST API 7.1 that the platform
needs (work items, their history, WIQL queries, links, comments, the process and identities), with
its own SQLite file (SA §22.2, feature 015). The platform's tracker adapter (feature 016) talks to
it exactly as it would talk to `dev.azure.com`; pointing the adapter at real ADO changes its base
URL and token, nothing else.

**What it is not.** It knows nothing of the lifecycle, the policy or decision rights. A work item
is data: the Epic's states are the terminal stages only because the seed file says so. It imports
nothing from the platform and the platform imports nothing from it (boundary tests on both
sides).

The design is in `specs/015-ado-sim-api/` (spec, plan, research, data model, contracts).

## Run it

```bash
cd ado_sim
uv sync --locked
export ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db
export ADO_SIM_TOKEN_KEY="$(openssl rand -hex 32)"    # keep it: tokens are signed with it
uv run ado-sim migrate
uv run ado-sim seed --if-new --file seed/demo.yaml
uv run ado-sim token issue adlc-platform@adlc.demo    # printed once, never stored
uv run ado-sim serve                                  # http://127.0.0.1:8600
```

`make local` does the same with the rest of the platform (`ado-sim` in `deploy/Procfile.local`),
and `make up` runs it as the `ado-sim` compose service (see `deploy/README.md`).

Try it:

```bash
TOKEN=<the issued token>
BASE="http://127.0.0.1:8600/adlc-demo/Agentic%20ADLC/_apis/wit"
curl -s -u ":$TOKEN" -H "Content-Type: application/json-patch+json" \
  -d '[{"op":"add","path":"/fields/System.Title","value":"First use case"}]' \
  "$BASE/workitems/\$Epic?api-version=7.1"
curl -s -u ":$TOKEN" "$BASE/workitems/1/updates?api-version=7.1"
```

## Commands

| Command | Does |
| --- | --- |
| `ado-sim migrate` | create the database file if missing and apply pending migrations |
| `ado-sim seed --file <yaml> [--if-new]` | load a seed file into an empty database; `--if-new` does nothing when already seeded |
| `ado-sim reset --yes` | remove all data and seed again from `ADO_SIM_SEED_FILE` |
| `ado-sim token issue <unique-name> [--label <text>]` | print a new token for an identity, once |
| `ado-sim token revoke <token-id>` | revoke a token |
| `ado-sim token list [<unique-name>]` | list token ids, identities, labels and times (never the tokens) |
| `ado-sim serve` | run the API |
| `ado-sim export-openapi [--check]` | write `contract/openapi.json`, or fail if it differs from what the app serves |

Exit codes: 0 done, 1 refused, 2 settings or invalid input.

## Settings

Environment only, prefix `ADO_SIM_`; the simulator reads no `ADLC_*` setting.

| Name | Default | Notes |
| --- | --- | --- |
| `ADO_SIM_DB_PATH` | required | the SQLite file |
| `ADO_SIM_TOKEN_KEY` | required, at least 32 characters | the key of the token HMAC; a secret |
| `ADO_SIM_HOST` | `127.0.0.1` | `0.0.0.0` in the container |
| `ADO_SIM_PORT` | `8600` | |
| `ADO_SIM_SEED_FILE` | `seed/demo.yaml` | used by `reset` |
| `ADO_SIM_BUSY_TIMEOUT` | `30s` | how long a writer waits for the lock |
| `ADO_SIM_LOG_LEVEL` | `INFO` | |
| `ADO_SIM_OTLP_ENDPOINT` | unset | when set, traces go to Phoenix (project `ado-sim`) |

## The seed file

`seed/demo.yaml` declares the organisation (`adlc-demo`), the project (`Agentic ADLC`), its area
paths, the process (Agile types; the Epic's states are the terminal stages T0–T9, then `Closed` and
`Removed`), the `Custom.Adlc*` fields feature 016 maps, and the identities: the platform's service
account `adlc-platform@adlc.demo` and one demo user per role. It holds no token and no secret; the
seed refuses keys that look like one.

## Tokens

Clients send a personal access token as ADO accepts it: Basic authentication with any user name
and the token as password, or `Authorization: Bearer <token>`. Tokens are random, printed once by
`ado-sim token issue`, and stored only as an HMAC-SHA256 with `ADO_SIM_TOKEN_KEY`. Changing the key
invalidates every token. A missing, unknown or revoked token gets `401` with an empty body.
`GET /health` and `GET /openapi.json` need no token.

## The contract

- `contract/openapi.json`: the published description; `GET /openapi.json` serves the same
  document, and `ado-sim export-openapi --check` (in `make ado-sim-check`) keeps them equal.
- `contract/fixtures/<operation>/<case>.json`: a request and the response it gets from a freshly
  seeded simulator, one per operation and per refusal; the format is in `contract/fixtures/README.md`.
  `tests/contract/test_fixtures.py` replays them all; feature 016's adapter tests reuse them.
- `contract/differences.md`: every known difference from real ADO, to confirm before a real
  tracker is connected.

**Polling for changes.** Query
`[System.ChangedDate] >= '<asOf of the previous answer>'` with `timePrecision=true`, then read each
returned item's updates and de-duplicate by (id, rev). Changed dates increase in commit order
across all items and `asOf` is the latest change the query saw, so no change is missed
(research R-06).

## Checks

`make ado-sim-check` from the repository root (part of `make check`): ruff, format, mypy, pytest
(unit, API, contract and property tests), coverage at least 80% and the contract check. The
property tests report their measurements (SC-004 p95 timings, SC-006 seed and reset times) in the
test summary.
