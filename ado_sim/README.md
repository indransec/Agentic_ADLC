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
| `ado-sim password set <user> \| --all [--stdin]` | set a page password (017), stored as a hash |
| `ado-sim password clear <user>` | remove it and end the user's page sessions |
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
seed refuses keys that look like one. Two sections serve the pages: `board:` (017) and `form:`
(018: the work item form's sections per type, each a title and field references, validated against
the process). The decision field's `allowed_values` are the platform's tracker mapping values; a
platform contract test keeps the two files in step (change the mapping first).

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

## Pages (features 017 and 018)

The simulator also serves pages for people, at the addresses ADO uses:

| Page | Address |
| --- | --- |
| Sign in | `/_signin` (the start page redirects there without a session) |
| The board | `/{organization}/{project}/_boards/board` (`?area=<path>` filters) |
| The backlog | `/{organization}/{project}/_backlogs/backlog` (`?area=<path>` filters) |
| A work item | `/{organization}/{project}/_workitems/edit/{id}` (the form) |

**Signing in.** Pick a seeded user (the platform's service account, `service: true` in the seed, is
never offered) and give one of: a page password (`ado-sim password set <user>`, or `--all` for
every demo user; stored only as an scrypt hash), the shared demo password when
`ADO_SIM_DEMO_PASSWORD` is set (off by default; a warning is logged at start), or one of the user's
personal access tokens. Every refusal has the same message. Sessions last
`ADO_SIM_PAGE_SESSION_TTL` (8h) from sign-in; signing out, clearing the password
(`ado-sim password clear <user>`) or revoking a token ends them. Everything a person does on a
page is recorded as theirs, exactly as through the API.

**The board** shows one column per state of the seed's board type (`board:` in the seed: type,
card fields, collapsed states, refresh interval), one card per item, and refreshes its columns
every few seconds. Cards cannot be moved: columns belong to the platform (feature 016). A person
can create an Epic from the board, which the platform registers as a use case.

**The backlog** (018) shows each item of the board type without a parent, with its descendants
(run items, their clarification items) as a tree that collapses level by level, filtered by area and
refreshed like the board.

**The work item form** (018) shows the item's fields in the sections of the seed's `form:` layout
(then "Other fields"), with an input for each field's type: a list for allowed values (the decision),
states and areas, a user list for identities, text boxes otherwise; system fields are read-only. A
save sends only the fields the person changed, as them, checked against the revision the form was
opened at: if the item changed meanwhile, the form shows the current item with their changes kept.
HTML fields are edited as plain text and shown with a small safe subset (paragraphs, lists, bold,
italic, http(s) links); comments are always plain text. The form also adds comments and shows the
history (who, when, old and new values). Any editable field can be changed, as in ADO; the platform
sets back the fields it owns, with a comment (feature 016).

The pages use Jinja2 templates (autoescaped), HTMX 2.0.4 and one stylesheet, all served by the
simulator itself (`/_static/`); no external network. They send a strict content security policy.

## Dependencies

| Dependency | Licence | Use |
| --- | --- | --- |
| FastAPI, uvicorn, pydantic | MIT, BSD-3-Clause, MIT | API |
| Jinja2 3.1.6 (MarkupSafe) | BSD-3-Clause | page templates (017) |
| python-multipart 0.0.32 | Apache-2.0 | page forms (017) |
| htmx 2.0.4 (vendored, `pages/static/`) | 0BSD | board refresh (017) |
| ruamel.yaml | MIT | seed file |
| OpenTelemetry | Apache-2.0 | optional traces |

## Checks

`make ado-sim-check` from the repository root (part of `make check`): ruff, format, mypy, pytest
(unit, API, contract and property tests), coverage at least 80% and the contract check. The
property tests report their measurements (SC-004 p95 timings, SC-006 seed and reset times) in the
test summary.
