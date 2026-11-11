---
id: PB-T2-01
version: "1.1.0"
title: T2 architecture
owner_role: adlc_coe
status: active
---
# T2 architecture

## Purpose

Produce the design contract the build terminal (T3) implements and later terminals check against:
components, data handling, the agentic pattern, models, tools and their contracts, memory,
human-in-the-loop points, token budget, security, observability and deployment. Every T1
requirement is mapped to a design decision.

## Inputs

- T0 and T1 evidence (requirements, NFRs, autonomy levels, data access).
- Reference architectures, ADRs, platform standards and the approved MCP server and tool list in
  the grounding scope.

## Steps per artifact

1. **solution_overview** (`aspect, description`): purpose, users, scope, out of scope, key
   constraints.
2. **system_architecture** (`component, responsibility, technology, interfaces`): agent, tools,
   model gateway, data stores, UI or channel, observability.
3. **data_strategy** (`data_element, classification, retention, access_policy, residency`).
   `classification` is a data class id and never above the highest class T0 marked `approved` in
   its data access.
4. **agentic_pattern** (`decision_id, pattern, rationale, genai_principle`): the pattern from the
   agentic patterns playbook (PB-T2-02) and why a simpler one does not fit.
5. **model_strategy** (`use, model, version, fallback, routing_rule`): model tier per use, a
   fallback for every model, and when to route to it (outage only, never on refusal).
6. **tool_api_contracts** (`tool_id, mcp_server, operation, auth, input_schema, output_schema,
   error_semantics`). `mcp_server` is an id from the approved MCP server list, or `new` for a tool
   that must be registered first. Every contract states its auth and its error semantics.
7. **memory_context_strategy** (`memory_type, store, scope, ttl`): retention consistent with the
   data strategy.
8. **hitl_design** (`action, trigger, approver_role, timeout_behaviour`): one row for every T1
   autonomy action with `hitl_required: true`, with the same action name.
9. **token_budget** (`task, max_tokens, max_cost_usd, on_exceed`): numbers for every task; no
   `max_cost_usd` above T1's cost NFR target.
10. **security_architecture** (`threat, control, layer`): prompt injection, data leakage, tool
    misuse, identity, supply chain; include a kill switch.
11. **observability_design** (`signal, source, metric, sink, alert`).
12. **rai_metric_emission** (`rai_metric, emission_point, frequency`): every RAI metric of T1.
13. **deployment_architecture** (`environment, purpose, infra, data_allowed`): `poc`, `dev`, `test`,
    `prod` at least.
14. **design_decisions** (`decision_id, decision, req_ids, status`): `req_ids` lists T1 requirement
    ids separated by commas; every functional requirement id appears at least once. `status` is
    `proposed` or `accepted`.

## When to ask

Ask the solution architect when a platform standard or approved tool is missing for a needed
capability; ask the data owner about a data element's classification or retention. List where you
looked.
