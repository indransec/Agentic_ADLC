# Quickstart: Pilot Environments

## 1. Offline

```bash
make check     # includes the pilot project: lint, types, tests, and the boundary and isolation tests
```

## 2. Live (demo host)

```bash
make up        # adds pilot-dev, pilot-test, pilot-prodsim, pilot-traffic on the pilot network
pt() { docker compose -f deploy/compose.yaml --env-file .env run --rm pilot-tools "$@"; }   # bash or zsh
pt pilot-build --fill fills/default                      # prints sha256:<hex>
pt pilot-build --fill fills/default                      # same hash (SC-001)
pt pilot-env pilot-dev create --package sha256:<hex>
pt pilot-env pilot-test create --package sha256:<hex>
pt pilot-split full --stable sha256:<hex>                # prod-sim deploys by role, not by environment
pt pilot-env pilot-dev status && pt pilot-split status   # each reports the same hash (SC-002)
pt pilot-incidents --seed 7 --size 200 --out /data/golden.jsonl
```

**Rollout and traffic:**

```bash
pt pilot-build --fill fills/variant                       # a second package
pt pilot-split canary --share 0.2 --candidate sha256:<other>
pt pilot-traffic-ctl rate 5 && pt pilot-traffic-ctl start
pt pilot-traffic-ctl metrics                              # rate within ±10%; candidate share 15–25% (SC-003, SC-004)
```

**Faults:**

```bash
pt pilot-fault model_swap trigger    # routing_accuracy falls below baseline within 5 minutes (SC-005)
pt pilot-fault model_swap revert
pt pilot-fault pii_leak trigger      # pii_leak_rate ≥ 10% (SC-006)
pt pilot-fault pii_leak revert
```

**Isolation (SC-007):** from `api` and `orchestrator`, connecting to `pilot-prodsim:8100` fails;
from `pilot-prodsim`, connecting to `postgres:5432`, `api:8000` and `knowledge:8020` fails.
