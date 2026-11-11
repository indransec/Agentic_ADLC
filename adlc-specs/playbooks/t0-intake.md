---
id: PB-T0-01
version: "1.1.0"
title: T0 intake
owner_role: adlc_coe
status: active
---
# T0 intake

## Purpose

Turn the business owner's free-text description into a reviewable intake: what problem is being
solved, whether an agent is the right tool, what value is expected, how risky it is, which data it
needs, whether it is feasible, and who is responsible for what. The intake is the evidence every
later terminal builds on, so state facts with their source and say what is unknown.

## Inputs

- The intake text and the business owner named on the use case.
- Enterprise knowledge in the grounding scope: business capabilities, strategy, policies and the
  existing agent portfolio. Search before you assume; cite what you use.
- Answers to earlier clarifications, failed controls and, on rework, the approvers' comment.

## Steps per artifact

1. **intake_card** (`attribute, value, source, confidence`). One row per attribute: use case name,
   business owner, business unit, capability (from the capability map), process affected, users,
   channel, volume per month, current handling time, desired outcome. `source` is `intake`,
   `clarification`, or `<source>:<document>`. `confidence` is `high` (stated or cited), `medium`
   (inferred from a cited document) or `low` (assumed; say why in `value`).
2. **business_problem** (`problem, industry_challenge, use_case_type, affected_users`). State the
   problem as a measurable gap ("12 minutes per claim triage, 40% re-work"), not as a solution.
   `use_case_type` is `vertical` (one business process) or `horizontal` (cross-functional).
3. **agentic_suitability** (`criterion, score_1_5, rationale`). Score every criterion of the
   agentic suitability rubric (playbook PB-T0-02). The mean must be at least 3 for an agent to be
   justified; if it is lower, say plainly which simpler option fits better.
4. **value_hypothesis** (`value_driver, metric, baseline_estimate, target_estimate`). At least one
   driver per expected benefit (time, cost, quality, experience). Every row has a metric and
   numbers; mark estimates you could not source with "(estimate)".
5. **risk_classification** (`dimension, rating, rationale, tier`). Rate each dimension of the risk
   classification playbook (PB-T0-03). Every row's `tier` is `low`, `medium` or `high`; the
   overall tier is the highest dimension tier and is stated in a final row with dimension
   `overall`.
6. **data_access** (`data_source, classification, owner, access_status`). Every data source the
   agent would read or write. `classification` is a data class id (`public`, `internal`,
   `synthetic_or_masked`, `confidential_masked`, `confidential`, `restricted`) taken from the data
   classification policy; `owner` is the accountable role or named owner from the policy;
   `access_status` is `approved`, `requested` or `not_requested`. Never invent an owner.
7. **initial_rai_security** (`consideration, concern, initial_mitigation`). Fairness,
   transparency, privacy, safety, security (prompt injection, data leakage), and human oversight;
   one concrete concern and mitigation each.
8. **feasibility** (`dimension, assessment, blocker`). Data availability, integration, skills,
   timeline, cost. `blocker` is `none` or the specific blocker.
9. **raci** (`activity, responsible, accountable, consulted, informed`). One row per lifecycle
   activity (intake, requirements, design, build, evaluation, assurance, release, operations).
   Exactly one accountable role per activity; use role ids from the role catalogue.

## Duplicate check

Search the agent portfolio for agents with the same capability and users. If one is similar, name
it in `feasibility` (dimension `reuse`) with what differs.

## When to ask instead of assuming

Ask a clarification when a fact needed by a mandatory artifact is missing after you have searched:
the data owner, the users and volume, the decision the agent would take, or the business owner's
target. Address it to the role that owns the fact; facts about the intake itself go to the
business owner. List where you looked.
