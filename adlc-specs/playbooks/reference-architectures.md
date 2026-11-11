---
id: PB-T2-03
version: "1.1.0"
title: Reference architectures
owner_role: adlc_coe
status: active
---
# Reference architectures

## Purpose

Reuse an approved reference architecture instead of designing from scratch, and record any
deviation as a design decision.

## Steps

1. Search the architecture repository for a reference architecture matching the pattern and the
   domain, and for ADRs that apply (model gateway, data residency, observability).
2. Base `system_architecture` and `deployment_architecture` on it; cite it.
3. For every deviation, add a `design_decisions` row explaining why, with the requirement ids that
   need it.
4. Check every tool against the approved MCP server and tool list; mark missing ones `new` in
   `tool_api_contracts` and add a decision to register them.

## Baseline every design keeps (platform standards)

- All model calls go through the model gateway with a fallback.
- Every agent emits traces with the run id and RAI metrics.
- Every environment has a kill switch and a rollback.
- Personal data is masked before it reaches a model unless the data strategy allows it.

## When to ask

Ask the solution architect when no reference architecture fits and the deviation is large.
