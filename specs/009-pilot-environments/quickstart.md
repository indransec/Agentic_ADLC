# Quickstart: Pilot Environments

## 1. Offline

```bash
make check     # includes the pilot project: lint, types, tests, and the boundary and isolation tests
```

## 2. Live (demo host)

```bash
make up        # adds pilot-dev, pilot-test, pilot-prodsim, pilot-traffic on the pilot network
P="docker compose -f deploy/compose.yaml --env-file .env run --rm pilot-tools"
$P pilot-build --fill fills/default                      # prints sha256:<hex>
$P pilot-build --fill fills/default                      # same hash (SC-001)
$P pilot-env pilot-dev create --package sha256:<hex>
$P pilot-env pilot-test create --package sha256:<hex>
$P pilot-env pilot-prodsim status                         # each reports the same hash (SC-002)
$P pilot-incidents --seed 7 --size 200 --out /data/golden.jsonl
```

**Rollout and traffic:**

```bash
$P pilot-build --fill fills/variant                       # a second package
docker compose ... exec pilot-prodsim ...                 # or: $P pilot-split canary --share 0.2 --candidate sha256:<other>
$P pilot-traffic-ctl rate 5 && $P pilot-traffic-ctl start
$P pilot-traffic-ctl metrics                              # rate within ±10%; candidate share 15–25% (SC-003, SC-004)
```

**Faults:**

```bash
$P pilot-fault model_swap trigger    # routing_accuracy falls below baseline within 5 minutes (SC-005)
$P pilot-fault model_swap revert
$P pilot-fault pii_leak trigger      # pii_leak_rate ≥ 10% (SC-006)
$P pilot-fault pii_leak revert
```

**Isolation (SC-007):** from `api` and `orchestrator`, connecting to `pilot-prodsim:8100` fails;
from `pilot-prodsim`, connecting to `postgres:5432`, `api:8000` and `knowledge:8020` fails.
