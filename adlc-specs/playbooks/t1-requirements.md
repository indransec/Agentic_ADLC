---
id: PB-T1-01
version: "1.1.0"
title: T1 requirements
owner_role: adlc_coe
status: active
---
# T1 requirements

## Purpose

Turn the approved intake (T0 evidence) into testable requirements, measurable targets and the
boundaries of what the agent may do. Everything here is traceable to T0's problem and value
hypothesis and is checked again at evaluation (T4) and in operation (T8).

## Inputs

- T0's evidence: intake card, business problem, value hypothesis, risk classification, data access.
- The use case's risk tier (it sets parameter limits; see below).
- Process documents, SOPs and related epics in the grounding scope.

## Steps per artifact

1. **functional_requirements** (`req_id, description, priority, persona, acceptance_criteria`).
   Ids `FR-01`, `FR-02`, ... Priority `must`, `should` or `could`. Each acceptance criterion is a
   testable statement ("returns the claim status within 5 s for a valid claim id"). Every T0 problem
   statement is covered by at least one `must`.
2. **non_functional_requirements** (`nfr_id, category, requirement, target, unit`). Categories:
   `performance`, `availability`, `scalability`, `cost`, `security`, `privacy`. `target` is a number.
   Include at least one `cost` row: the maximum cost per task in USD (unit `usd_per_task`); T2's
   token budget must stay within it.
3. **behavioural_requirements** (`beh_id, situation, expected_behaviour, prohibited_behaviour`).
   Cover out-of-scope requests, unsafe or abusive requests, missing information, low confidence and
   escalation to a person.
4. **autonomy_levels** (`action, autonomy_level, hitl_required, boundary`). One row per action the
   agent can take; levels from the autonomy levels playbook (PB-T1-02), as a number. `hitl_required`
   is `true` or `false`. No level may exceed the tier's maximum: low 2, medium 3, high 4. Any
   irreversible action (payments, account changes, sending to customers) has `hitl_required: true`.
5. **kpis** (`kpi_id, kpi, baseline, target, unit, measurement_source`). From T0's value
   hypothesis; `baseline` and `target` are numbers; `measurement_source` names where it is measured.
6. **eval_thresholds** (`metric, operator, threshold, dataset_scope`). From the metric catalogue
   (PB-T1-03). `operator` is `>=`, `<=`, `>` or `<`; `threshold` is a number.
7. **rai_thresholds** (`metric, operator, threshold, slice`). Responsible-AI metrics from the
   metric catalogue, with the slice they apply to (e.g. `all`, `language=fr`, `persona=elderly`).
8. **user_experience** (`journey, step, channel, expected_experience`). The main journey plus the
   error and handoff-to-person states.
9. **acceptance_and_failure** (`scenario_id, scenario, type, expected_outcome`). `type` is `happy`,
   `edge`, `failure`, `adversarial` or `out_of_scope`. At least the tier's minimum number of
   scenarios: low 15, medium 30, high 50. Mix all types; at least a fifth are failure or adversarial.

## When to ask

Ask the product owner when a target, priority or persona is missing and cannot be derived from T0
or the documents. Ask the business owner about business rules from the intake. List where you looked.
