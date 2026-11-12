# Quickstart: MCP Servers (feature 010)

## 1. Offline (`make check`)

- Unit: run tokens (sign, verify, expiry, wrong scope, tampering); argument filtering and bound
  values; harness metrics on fixed answers; red-team checks; personal-data masking; monitor
  evaluation; Git branch rules (no `main`, layout only, moved branch).
- Integration (testcontainers Postgres and fake pilot endpoints): every tool through the platform
  gate and the MCP client against both servers; refusals at the gate and at the server; records in
  `tools.tool_call` and `tools.tool_result`; enterprise mock records; evidence from the bridge.
- Pilot suite: `pilot-lab` build, packages and datasets; the kill switch; feedback.
- Static: only `pilot-bridge` and `jaeger` on both networks; no ports; no Docker socket; the bridge
  has no database settings.

## 2. Live (demo host)

```bash
make up                         # adds tools, pilot-bridge and pilot-lab
```

`adlc-tools-probe` (a dev command, not a service) calls a tool as a named terminal for a use case,
through the real gate, run token, bound values and records. The tool servers publish no ports, so
it runs in the orchestrator container on the platform network:

```bash
P() { t=$1; shift; docker compose -f deploy/compose.yaml --env-file .env run --rm -T orchestrator \
      adlc-tools-probe --usecase UC-DEMO --terminal "$t" "$@"; }
pt() { docker compose -f deploy/compose.yaml --env-file .env run --rm pilot-tools "$@"; }   # pilot commands
P T3 git_write --files /app/fill --arg message=fill           # writes a fill (mount it)
P T3 ci_run                                                   # checks pass, prints sha256:<hex> (= pilot-build)
P T3 pilot_env_create --arg package_hash=sha256:<hex>         # dev running that hash
P T3 cd_deploy                                                # refused (scope) — SC-001
P T4 pilot_env_create                                         # test runs the candidate hash
P T4 harness_run --arg dataset_id=golden                      # identical twice (SC-004)
P T5 redteam_harness_run                                      # pii_extraction 0%
pt pilot-fault pii_leak trigger; P T5 redteam_harness_run      # pii_extraction > 0 (SC-005)
P T7 cd_deploy                                                # only the T6 hash (SC-006)
P T6 monitoring_configure --arg metric=routing_accuracy --arg "operator=<" --arg threshold=0.8 --arg window_s=120
pt pilot-fault model_swap trigger; P T8 monitoring_read       # fired within 5 minutes (SC-007)
P T6 servicenow_change_create --arg summary=Release --arg window_start=... --arg window_end=... --arg risk=low
```

Then check: `tools.tool_call` has a row per call (SC-002); the decision for PRE-T3-03 and PRE-T3-04
is not labelled synthetic (FR-009); a full traffic run's telemetry and tool outputs contain no
incident text (SC-008); a token copied from one call is refused for another tool or after five
minutes (SC-001).
