# Contract: Pilot Additions (feature 010)

Pilot-side operations the bridge calls. Pilot network only (009 contracts/pilot-api.md applies).

## `pilot-lab` (new service; port 8300)

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /health` | — | `{status}` |
| `POST /build` | `{files: {path: text}}` (the fill layout) | `{checks: [{name: validate, build, reproducible, smoke; passed; detail}], package_hash?}`; a failed `validate` names the fill part |
| `GET /packages/{hash}` | — | manifest, or `404` |
| `GET /datasets` | — | `[{id, version, seed, size, pii_share, sha256, scored_fields, slices}]` from `pilot/datasets.yaml` |
| `GET /datasets/{id}` | — | `{dataset, rows}`; each row is an incident plus the labels `expected`, `planted_pii`, `edge_case` and `synthetic`, which the harness keeps for scoring and never sends; `404` if unknown |

## Prod-sim host additions

| Method and path | Body | Answer |
| --- | --- | --- |
| `POST /kill` | `{action: activate or release, reason}` | `200 {active}`; `409` activating twice; while active `/triage` answers `503 stopped by the kill switch`; recorded in `faults.jsonl` |

## Traffic generator addition

| Method and path | Answer |
| --- | --- |
| `GET /feedback?limit=N` | Seeded synthetic ratings (1–5) and comments derived from answer correctness, `synthetic: true` |

## Commands

`pilot-kill release --reason <text>`: a person releases the kill switch.
