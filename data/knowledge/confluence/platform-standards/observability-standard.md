---
title: "Standard: observability"
data_class: internal
synthetic: true
collections: []
version: "1.0.0"
---
# Standard: observability

## Signals

Every agent emits OpenTelemetry traces with the run id, metrics for latency, cost and task success,
and RAI metrics (toxicity, PII leakage, jailbreak attempts) to the monitoring platform. Alerts page
the service owner.
