# Quickstart: Terminal Agents T3–T5 (feature 011)

## 1. Offline (`make check`)

- Unit: `rows_match`; evidence mapping; table import; harness catalogue metrics and calibration.
- Integration: T3, T4, T5 with scripted replies through the runtime, gate, tokens and the bridge
  over the fake pilot: artifacts valid, controls reading real evidence (not synthetic), a
  mismatched number failing, a weaker candidate recommended for rework to T3, a T5 gap ending as
  an exception with waiver, out-of-scope calls refused and recorded.
- Replay: `it-service-desk` offline through T5 sign-off.
- Pilot: CI report checks.

## 2. Live (dev model)

```bash
make up
docker compose -f deploy/compose.yaml --env-file .env run --rm -T orchestrator \
  adlc-replay --profile dev --usecase it-service-desk     # T0..T5 with the dev model
```

Check: T3's candidate hash equals CI's and dev runs it (SC-002); T3–T5 control decisions on
`ci`, `sbom`, `harness`, `redteam`, `dlp` are not synthetic (SC-003); the report shows cost and
tool calls per terminal (SC-007).
