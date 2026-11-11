# Contract: Pilot APIs and Commands (feature 009)

These APIs are reachable only on the `pilot` network. Feature 010's MCP servers call them for the
platform. No platform service calls them directly.

## Environment host (`pilot-dev`, `pilot-test`, `pilot-prodsim`; port 8100)

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /health` | — | `{status, environment}` |
| `POST /environment` | `{package_hash, settings?}` (dev and test) | `201 {environment, package_hash, replicas, settings}`; `404` unknown hash; `422` undeclared setting or value; `409` already running |
| `GET /environment` | — | `{environment, package_hash, replicas: [{id, healthy}], settings, started_at}` or `404` |
| `DELETE /environment` | — | `204`; nothing of it remains running |
| `POST /deployments` | `{package_hash, role: stable or candidate}` (prod-sim) | `201`; `404` unknown hash |
| `PUT /split` | `{mode: shadow, canary or full, share?}` (prod-sim) | `200 {mode, share, stable, candidate}`; `404` if the candidate is missing; `422` bad mode or share |
| `GET /split` | — | Current split and the last changes |
| `POST /triage` | An incident (data-model.md) | The triage answer, with `package_hash` |
| `POST /faults/{fault}` | `{action: trigger or revert, parameters?}`; `fault` is `model_swap` or `pii_leak` | `200` record; `409` when already active, or reverting an inactive fault |
| `GET /faults` | — | Active faults and the last records |

Every create, tear down, split change and fault is appended to the records (data-model.md).

## Traffic generator (`pilot-traffic`; port 8200)

| Method and path | Body | Answer |
| --- | --- | --- |
| `PUT /rate` | `{per_second}` (0.1–50) | `200` |
| `POST /start`, `POST /pause` | — | `200 {running}` |
| `GET /metrics` | — | `{sent, answered, failed, timed_out, rate_actual, routing_accuracy, pii_leak_rate, window_s, by_package: {...}}` |

## Commands (run on the pilot network: `docker compose run --rm pilot-tools <command>`)

| Command | Does |
| --- | --- |
| `pilot-build --fill <dir> [--registry <dir>]` | Validates the fill, builds the package, prints `package_hash`; exit 1 with the failing fill part |
| `pilot-incidents --seed N --size M [--pii-share P] --out <file>` | Writes reproducible synthetic incidents |
| `pilot-env <host> create|status|delete [--package <hash>] [--set k=v]` | Calls a host's environment operations |
| `pilot-split <mode> [--share S] [--candidate <hash>]` | Sets prod-sim's split |
| `pilot-fault <model_swap|pii_leak> trigger|revert` | Calls prod-sim's fault operation |
| `pilot-traffic-ctl rate|start|pause|metrics` | Calls the traffic generator |
