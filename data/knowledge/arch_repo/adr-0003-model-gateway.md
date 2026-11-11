---
title: "ADR-0003: all model calls through the gateway"
data_class: internal
synthetic: true
collections: [ADRs]
version: "1.0.0"
---
# ADR-0003: all model calls through the gateway

## Decision

Agents never call model providers directly; the gateway enforces model approval, data class limits,
token budgets and fallback.
