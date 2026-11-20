# Phoenix (trace collector)

[Arize Phoenix](https://github.com/Arize-ai/phoenix) receives the OpenTelemetry traces of the
platform and the pilot, stores them (its own SQLite file in `PHOENIX_WORKING_DIR`) and serves them
back: a web UI, and the REST API the pilot bridge reads for `observability_traces` (feature 010).
It replaces Jaeger, so the platform's infrastructure is Python only.

- Ingest: OTLP over HTTP at `http://<host>:6006/v1/traces` (`ADLC_OTLP_ENDPOINT`,
  `PILOT_OTLP_ENDPOINT` point at `http://<host>:6006`; the exporters add `/v1/traces`).
- Projects: a span's project is its `openinference.project.name` resource attribute
  (`OTEL_RESOURCE_ATTRIBUTES`); compose names the platform `adlc-platform` and each pilot
  environment after its service (`pilot-triage-dev`, `-test`, `-prod-sim`). The bridge reads the
  project named `ADLC_BRIDGE_PILOT_SERVICE`.
- Read: `GET /v1/projects/{project}/spans` (`ADLC_BRIDGE_PHOENIX_URL`); UI on the same port.

This folder is its own uv project, pinned and locked, so Phoenix's dependencies never mix with the
platform's. Without Docker: `make phoenix` (or `cd deploy/phoenix && uv run phoenix serve`).
