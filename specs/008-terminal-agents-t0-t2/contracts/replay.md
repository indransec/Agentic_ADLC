# Contract: `adlc-replay` (feature 008)

Replays the reference use cases through T0–T2 and writes a quality report (FR-018 to FR-020).

```text
adlc-replay [--set data/reference_usecases] [--only <id> ...]
            (--profile <name> [--record <dir>] | --recording <dir>)
            [--baseline <report dir>] [--out reports/replays]
```

| Option | Meaning |
| --- | --- |
| `--profile` | Live replay with this model profile (e.g. `dev`); needs its keys in the environment |
| `--record` | With `--profile`: also save every model reply as a recording |
| `--recording` | Replay from recordings; no provider and no keys |
| `--baseline` | An earlier report; mark where the reviewer's recommendation changed |
| `--only` | Limit to some use cases |

**Behaviour**: for each use case:
1. Submit as the business owner.
2. Drain the worker.
3. Answer each clarification from the file's `answers` for the addressed role. A clarification
   for a role with no prepared answer stops that use case as "unanswered clarification" (exit 1).
4. When a terminal awaits sign-off, read the report data, then pass it with the approvers its
   sign-off rule needs (typing `approver_fields`), until T2's review is recorded.

The tool runs against the database and knowledge server of the environment (`.env`), with its
own worker. It refuses to start while another orchestrator worker is active (a fresh heartbeat),
because that worker would advance the replay's runs with its own models. With Compose:

```bash
docker compose -f deploy/compose.yaml --env-file .env stop orchestrator
# wait for the heartbeat to age (ADLC_HEARTBEAT_MAX_AGE, 30 s by default), then:
docker compose -f deploy/compose.yaml --env-file .env run --rm --no-deps \
  -v "$PWD/tests/fixtures/replays:/rec" -v "$PWD/reports:/out" \
  orchestrator adlc-replay --recording /rec --out /out/replays
docker compose -f deploy/compose.yaml --env-file .env start orchestrator
```

The replay acts as the people of the account file: for each role it needs, an account holding
it that has not approved the run yet. Its spans go to the same collector as the orchestrator's
(service `adlc-replay`).

**Exit codes**:
- `0`: every use case reached T2 sign-off with all mandatory artifacts present and all blocking
  controls passing.
- `1`: at least one did not.
- `2`: a configuration error.

**Output**: `report.json` and `report.md` under `--out/<timestamp>/` (data-model.md).
