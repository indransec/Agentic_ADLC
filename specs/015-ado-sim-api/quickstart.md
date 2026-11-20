# Quickstart: ADO Simulator API (015)

Validation scenarios that show the feature working end to end. Contracts:
[operations](contracts/operations.md), [WIQL](contracts/wiql.md),
[commands, settings and seed](contracts/cli-settings-seed.md); data: [data-model](data-model.md).

## 1. Checks

```bash
make ado-sim-check          # ruff, format, mypy strict, pytest, coverage >= 80% (ado_sim/)
make check                  # includes ado-sim-check; CI runs it on every push
```

Expected: all green; the test run includes the contract fixture replay (SC-001), polling
completeness (SC-002), concurrency (SC-003), timing (SC-004), restart (SC-005), token scan
(SC-007) and both import boundaries (SC-008).

## 2. Run it without Docker

```bash
cd ado_sim
export ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db
export ADO_SIM_TOKEN_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(40))")
uv run ado-sim migrate
uv run ado-sim seed --file seed/demo.yaml           # under 1 minute (SC-006)
TOKEN=$(uv run ado-sim token issue business.owner@adlc.demo --label quickstart)
uv run ado-sim serve &                               # http://127.0.0.1:8600
```

With the whole platform, `make local` starts it as the `ado-sim` process (`deploy/Procfile.local`).

## 3. Walk the API

Let `B=http://127.0.0.1:8600/adlc-demo/Agentic%20ADLC/_apis` and `A="-u :$TOKEN"`.

1. **Create an Epic** (US1):
   `curl $A -X POST "$B/wit/workitems/\$Epic?api-version=7.1" -H 'Content-Type: application/json-patch+json' -d '[{"op":"add","path":"/fields/System.Title","value":"UC-0001 Claims triage"}]'`
   → `200`, `id` 1, `rev` 1, state `T0 Intake & Qualification`.
2. **Move it with a revision check** (US1): patch `[{"op":"test","path":"/rev","value":1},
   {"op":"replace","path":"/fields/System.State","value":"T1 Requirements & Outcome"}]` → `200`, `rev` 2;
   send the same patch again → `412`, item still at `rev` 2.
3. **Read its history** (US2): `GET $B/wit/workItems/1/updates?api-version=7.1` → two updates,
   the second with `System.State` old `T0 Intake & Qualification`, new `T1 Requirements & Outcome`,
   `revisedBy` Business Owner; `GET .../revisions/1` → the item as created.
4. **Query** (US3): `POST $B/wit/wiql?api-version=7.1` with
   `{"query":"SELECT [System.Id] FROM workitems WHERE [System.WorkItemType] = 'Epic'"}` → `[1]`;
   a query with `EVER` → `400` naming `EVER`.
5. **Link and comment** (US4, US5): create a Feature with `/relations/-` to the Epic as parent;
   add a second parent → `400`; add a comment and list comments → one, by Business Owner.
6. **Identities** (US6): no token → `401`; `GET /adlc-demo/_apis/identities?searchFilter=General&filterValue=business.owner@adlc.demo&api-version=7.1`
   → the identity; `ado-sim token revoke <id>` → the next call with `$TOKEN` → `401`.
7. **Contract** (US8): `GET /openapi.json` equals `ado_sim/contract/openapi.json`
   (`uv run ado-sim export-openapi --check`).
8. **Restart and reset** (US7): stop and start `serve` → everything is still there;
   `uv run ado-sim reset` → refused; `uv run ado-sim reset --yes` → only the seed remains.

## 4. Compose

`make up` starts the `ado-sim` service (image `adlc-ado-sim:0.1.0`, volume `ado-sim-data`, port
`${ADO_SIM_PORT:-8600}`); issue a token with
`docker compose -f deploy/compose.yaml --env-file .env exec ado-sim ado-sim token issue <unique-name>`.

## Results

Walked live without Docker on 2026-11-20 (T056), macOS, Python 3.12, against a throwaway
database (`ADO_SIM_DB_PATH` in a temporary directory, so `data/local/` was left untouched) on
port 8600. Every step passed.

| Step | Result |
| --- | --- |
| 2. migrate, seed, token, serve | migration 1 applied; seeded `adlc-demo/Agentic ADLC` in 0.07 s (SC-006); a 52-character token printed once; `/health` → `{"status":"ok"}` |
| 3.1 create an Epic | `200`, id 1, rev 1, state `T0 Intake & Qualification` |
| 3.2 move with a revision check | `200`, rev 2; the same patch again → `412` `WorkItemRevisionMismatchException`; the item stays at rev 2 |
| 3.3 history | 2 updates; the second shows `System.State` from `T0 Intake & Qualification` to `T1 Requirements & Outcome`, revised by Business Owner; revision 1 is the item as created |
| 3.4 query | Epics → `[1]`; `EVER` → `400` naming `EVER` |
| 3.5 link and comment | a Feature with the Epic as parent → `200`; a second parent → `400` `WorkItemLinkException`; one comment, by Business Owner |
| 3.6 identities and tokens | no token → `401`; the identity search → Business Owner; after `ado-sim token revoke 1` the same token → `401` |
| 3.7 contract | `GET /openapi.json` equals `contract/openapi.json`; `export-openapi --check` up to date |
| 3.8 restart and reset | after stopping `serve` (port confirmed free) and starting it again: item 1 has 4 updates (3 revisions and the update from the Feature's link) and 1 comment; `reset` without `--yes` → exit 1; `reset --yes` → reseeded, no work items, 12 Epic states, earlier tokens gone |

Also on 2026-11-20: the `adlc-ado-sim:0.1.0` image built from `deploy/ado-sim.Dockerfile` and,
run alone with a throwaway volume, migrated, seeded, served `/health` as the non-root user
`adosim`, answered a token holder and refused a call without a token, and on a second start
reported "already seeded; nothing to do".

Note for anyone repeating the walk: stop `serve` by its own process (`.venv/bin/ado-sim serve`, or
Ctrl-C). Killing a `uv run` wrapper started in the background leaves the server running.
