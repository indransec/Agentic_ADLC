# adlc.observability

Logging and tracing (feature 001; constitution X, XI).

- `configure_logging(level)`: plain stdlib logging to stderr with a format that never includes headers. A filter drops credential-like record attributes (`authorization`, `password`, `token`, `credential_hash`).
- `setup_tracing(app, settings)`: one OpenTelemetry `TracerProvider` per app (`service.name=adlc-api`), batch-exported over OTLP/HTTP to `ADLC_OTLP_ENDPOINT` (Jaeger v2 in Compose). `/health` is not traced, and headers are never captured. Exporter failures become a rate-limited WARNING and never affect requests.

Later features add `run_id` attributes to agent and tool spans and write `run_activity` rows.
