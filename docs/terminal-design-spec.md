# Terminal-Based Agentic ADLC – Terminal Design Specification

Nov 4, 2026 · @Indrajit

## 1. Purpose and scope

This specification defines the ten terminals (T0–T9) of the enterprise agentic ADLC and the YAML spec that drives each one. The lifecycle orchestrator reads only these YAML files at runtime: a terminal's YAML decides when it may open, which agents run, what they may touch, which controls must pass, what evidence must exist, where the outcome routes, and how long it may take. Changing the lifecycle means changing YAML, not orchestration code.

**In scope:** terminal purpose, agent and human roles, YAML attributes per terminal, controls, evidence, outcome routing and timelines.

**Out of scope for this version:** orchestrator runtime selection, UI, ledger storage technology, and the contents of individual playbooks and checklists (referenced by ID here, authored separately).

**How a terminal executes** (identical for every terminal):

1. **Open** — orchestrator receives a trigger event and validates `prerequisites` against the evidence ledger.
2. **Build** — terminal agent and subagents produce the artifacts listed under `evidence.artifacts`, following `playbooks` and grounding on `knowledge_sources`.
3. **Automated controls** — policy engine evaluates `controls.automated` deterministically.
4. **Review** — common reviewer agent evaluates `controls.checklist` and recommends an outcome.
5. **Sign-off** — owners in `authorities.sign_off` approve, edit, reject with comment or terminate.
6. **Route** — orchestrator applies `outcome_model` and writes the final record to the ledger.

**Conventions:** `${T1.eval_thresholds.task_success}` references a value already in the ledger; `<risk_tier>` blocks vary by the T0 risk class; IDs such as `CHK-T4-03` reference checklist items maintained in the control library.

## 2. Terminal spec standard

Every terminal YAML has the same ten top-level blocks: `metadata` and `trigger` identify and start the terminal; the eight governance blocks below control it. The orchestrator rejects a YAML that is missing any required attribute.

| Block | Attribute | Type | Req. | Meaning |
| --- | --- | --- | --- | --- |
| metadata | id, name, version, purpose | string / semver | Y | Identity; version pinned per use-case instance |
| metadata | owner\_role, status | role / enum | Y | Spec owner; draft · active · deprecated |
| trigger | on | list of events | Y | Events that open the terminal (e.g. `T0.pass`, `T9.reentry.T3`) |
| trigger | mode, schedule | enum / cron | Y | event · scheduled · continuous |
| prerequisites | id, evidence\_ref, condition | string / expr | Y | Ledger evidence that must exist and satisfy the condition |
| prerequisites | on\_missing | enum | Y | block · warn |
| actors | agent, subagents | id + responsibility | Y | Terminal agent and its subagents |
| actors | reviewer, human\_roles (with RACI) | role list | Y | Reviewer agent and accountable humans |
| authorities | allow, deny | permission list | Y | What agents may and may not do; deny wins |
| authorities | data\_access, tool\_scopes | class / scope list | Y | Max data classification and MCP/tool scopes |
| authorities | sign\_off | roles, min\_approvers | Y | Who closes the terminal |
| authorities | status\_rights | map | Y | Which actor may set which outcome status |
| playbooks | id, ref, version, applies\_when | string / expr | Y | Procedures the agent follows |
| playbooks | grounding | MCP sources | N | Enterprise knowledge the agent may read |
| controls | automated | id, rule, severity | Y | Deterministic policy checks; blocking or advisory |
| controls | checklist | ref, items | Y | Reviewer agent checklist item IDs |
| controls | tiering | by risk tier | N | Control depth by T0 risk class |
| evidence | artifacts | id, format, columns, required | Y | Artifacts this terminal must produce |
| evidence | ledger | key, immutable, retention | Y | Where and how long evidence is kept |
| outcome\_model | pass, rework, exception, escalate, terminate | condition, set\_by, route, requires | Y | Routing per status |
| timeline | expected\_duration, reminders, escalate\_after | duration by tier | Y | SLA and timers |
| timeline | max\_rework\_cycles | int | Y | Default 3 → escalate |

**Base template** (each terminal in sections 4–13 fills this in):

```yaml
terminal:
  metadata: {id: Tn, name: <name>, version: 1.0.0, purpose: <question>, owner_role: <role>, status: active}
  trigger: {on: [<event>], mode: event}
  prerequisites:
    - {id: PRE-Tn-01, evidence_ref: <terminal.artifact>, condition: <expr>, on_missing: block}
  actors:
    agent: {id: tn-agent, model_tier: <tier>}
    subagents: [{id: <id>, responsibility: <text>}]
    reviewer: common-terminal-reviewer
    human_roles: [{role: <role>, raci: A}]
  authorities:
    allow: [<permission>]
    deny: [<permission>]
    data_access: {max_class: <class>}
    tool_scopes: [<mcp:scope>]
    sign_off: {roles: [<role>], min_approvers: 1}
    status_rights: {agent: [], reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures: [{id: PB-Tn-01, ref: <path>, version: <semver>}]
    grounding: [{mcp: <server>, scope: <path>}]
  controls:
    automated: [{id: CTL-Tn-01, rule: <expr>, severity: blocking}]
    checklist: {ref: checklists/tn.yaml, items: [CHK-Tn-01]}
    tiering: {high: {}, medium: {}, low: {}}
  evidence:
    artifacts: [{id: <id>, format: table, columns: [<col>], required: true}]
    ledger: {key: "${usecase_id}/Tn/${run_version}", immutable: true, retention: <period>}
  outcome_model:
    pass: {route: <Tn+1>}
    rework: {route_by_root_cause: {<cause>: <terminal>}}
    exception: {requires: [waiver_owner, expiry, compensating_control]}
    escalate: {when: "rework_count > 3", route: human_completion}
    terminate: {set_by: human, requires: [reason]}
  timeline: {expected_duration: {low: <d>, medium: <d>, high: <d>}, reminder_after: <d>, escalate_after: <d>, max_rework_cycles: 3}
```

## 3. Shared definitions

These definitions are referenced by every terminal YAML and live in `adlc/shared/*.yaml`.

**Outcome statuses**

| Status | Meaning | Set by | Default route |
| --- | --- | --- | --- |
| pass | All blocking controls met; owners approve | Owner (reviewer recommends) | Next terminal per `outcome_model.pass` |
| rework | Artifacts incomplete or defective | Owner, with mandatory comment | Root-cause terminal; comment injected as agent context |
| exception | Proceed with documented waiver | Owner + waiver approver | Next terminal; waiver re-checked at T6 and T8 |
| escalate | Rework limit exceeded, SLA breached, or dispute | Orchestrator (automatic) | Human completes artifacts, then owner decides |
| terminate | Use case stops | Owner only, with reason | Lifecycle closed; T9 retirement if anything is deployed |

**Role catalogue** (human roles referenced by `actors.human_roles`)

| Role ID | Typical holder |
| --- | --- |
| business\_owner | Use-case sponsor; owns value and terminate decision |
| product\_owner | Owns requirements, KPIs, backlog |
| solution\_architect | Owns T2 design and deviations |
| engineering\_lead | Owns build quality |
| qa\_eval\_lead | Owns datasets, test and eval evidence |
| security\_officer | Security assurance |
| privacy\_officer | Privacy / DPO |
| rai\_officer | Responsible AI assurance |
| compliance\_officer | Regulatory mapping |
| risk\_owner | Accepts residual risk on behalf of the business |
| release\_manager | Release readiness and change |
| service\_owner | Run-state accountability |
| sre | Platform reliability and deployment |
| data\_owner | Approves data use, retention and disposal |
| adlc\_coe | Owns specs, playbooks, checklists |

**Risk tiers** (set in T0, read by every later `controls.tiering` and `timeline` block)

| Tier | Typical profile | Effect on later terminals |
| --- | --- | --- |
| low | Internal users, no PII, read-only tools, autonomy ≤ L2 | Smoke red-team, single assurance sign-off, shortest SLA |
| medium | Customer-facing or PII, limited write actions | Standard red-team, security + privacy sign-off |
| high | Regulated data (PHI, financial), autonomous write actions, autonomy ≥ L3 | Full red-team, RAI board + CISO sign-off, mandatory shadow and canary |

**Evidence ledger:** one immutable record per terminal run, keyed `${usecase_id}/${terminal_id}/${run_version}`, holding artifacts, control results, reviewer findings, sign-offs and the final status. Later terminals read evidence only from the ledger. Retention defaults to 7 years for high tier and 3 years otherwise (to be confirmed, section 15).

## 4. T0 – Intake & Qualification

**Question:** should we do this at all? The lifecycle graph starts when a business owner submits a free-text use case. The T0 agent turns it into a qualified intake card, grounded on enterprise knowledge, and sets the risk tier that every later terminal reads.

**Exit criteria:** qualified use case with initial value and risk classification, or a documented terminate.

```yaml
terminal:
  metadata:
    id: T0
    name: Intake & Qualification
    version: 1.0.0
    purpose: Should we do this at all?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [usecase.submitted, T9.reentry.T0]
    mode: event
  prerequisites:
    - {id: PRE-T0-01, evidence_ref: intake.free_text, condition: "length >= 200 chars", on_missing: block}
    - {id: PRE-T0-02, evidence_ref: intake.business_owner, condition: "exists in directory", on_missing: block}
  actors:
    agent: {id: t0-intake-agent, model_tier: reasoning}
    subagents:
      - {id: problem-framer, responsibility: "business problem, industry challenge, vertical/horizontal"}
      - {id: suitability-assessor, responsibility: agentic vs RPA vs rules vs classic ML}
      - {id: value-modeller, responsibility: value hypothesis and articulation}
      - {id: risk-classifier, responsibility: risk tier and data classification}
      - {id: raci-mapper, responsibility: map ADLC activities to org stakeholders}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: business_owner, raci: A}
      - {role: product_owner, raci: R}
      - {role: solution_architect, raci: C}
      - {role: rai_officer, raci: C}
      - {role: adlc_coe, raci: I}
  authorities:
    allow: [read:knowledge_base, read:usecase_portfolio, write:T0.artifacts]
    deny: [write:any_other_terminal, contact:external_parties]
    data_access: {max_class: internal}
    tool_scopes: [mcp:sharepoint:read, mcp:confluence:read, mcp:portfolio:read]
    sign_off: {roles: [business_owner], min_approvers: 1}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T0-01, ref: playbooks/t0-intake.md, version: 1.0.0}
      - {id: PB-T0-02, ref: playbooks/agentic-suitability-rubric.md, version: 1.0.0}
      - {id: PB-T0-03, ref: playbooks/risk-classification.md, version: 1.0.0}
    grounding:
      - {mcp: confluence, scope: "/business-capabilities"}
      - {mcp: sharepoint, scope: "/strategy, /policies"}
      - {mcp: portfolio, scope: "existing agents (duplicate check)"}
  controls:
    automated:
      - {id: CTL-T0-01, rule: "all required artifacts present", severity: blocking}
      - {id: CTL-T0-02, rule: "risk_tier in [low, medium, high]", severity: blocking}
      - {id: CTL-T0-03, rule: "suitability_score >= 3 of 5", severity: advisory}
      - {id: CTL-T0-04, rule: "no duplicate agent in portfolio (similarity < 0.85)", severity: advisory}
    checklist:
      ref: checklists/t0.yaml
      items: [CHK-T0-01 problem is measurable, CHK-T0-02 agentic approach justified over simpler options, CHK-T0-03 value hypothesis has a metric, CHK-T0-04 risk tier rationale stated, CHK-T0-05 data sources and owners named, CHK-T0-06 RACI has one A per activity]
  evidence:
    artifacts:
      - {id: intake_card, format: table, columns: [attribute, value, source, confidence], required: true}
      - {id: business_problem, format: table, columns: [problem, industry_challenge, use_case_type, affected_users], required: true}
      - {id: agentic_suitability, format: table, columns: [criterion, score_1_5, rationale], required: true}
      - {id: value_hypothesis, format: table, columns: [value_driver, metric, baseline_estimate, target_estimate], required: true}
      - {id: risk_classification, format: table, columns: [dimension, rating, rationale, tier], required: true}
      - {id: data_access, format: table, columns: [data_source, classification, owner, access_status], required: true}
      - {id: initial_rai_security, format: table, columns: [consideration, concern, initial_mitigation], required: true}
      - {id: feasibility, format: table, columns: [dimension, assessment, blocker], required: true}
      - {id: raci, format: table, columns: [activity, responsible, accountable, consulted, informed], required: true}
    ledger: {key: "${usecase_id}/T0/${run_version}", immutable: true, retention: per_tier}
  outcome_model:
    pass: {route: T1, emits: [risk_tier, usecase_id]}
    rework: {route: T0, requires: [owner_comment]}
    exception: {requires: [waiver_owner, expiry, compensating_control]}
    escalate: {when: "rework_count > 3 or age > escalate_after", route: human_completion}
    terminate: {set_by: business_owner, requires: [reason], notify: [adlc_coe]}
  timeline:
    expected_duration: {low: 2d, medium: 3d, high: 5d}
    reminder_after: 2d
    escalate_after: 7d
    max_rework_cycles: 3
```

## 5. T1 – Requirements & Outcome

**Question:** what exactly must the agent achieve? T1 produces the requirement contract. Its thresholds (KPIs, eval, RAI) become machine-readable values that T4, T5 and T8 evaluate against automatically, so they must be numeric and unambiguous.

**Exit criteria:** requirement contract + approved outcome model, with every threshold recorded as a number.

```yaml
terminal:
  metadata:
    id: T1
    name: Requirements & Outcome
    version: 1.0.0
    purpose: What exactly must the agent achieve?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T0.pass, T0.exception, T9.reentry.T1, T4.rework.requirement]
    mode: event
  prerequisites:
    - {id: PRE-T1-01, evidence_ref: T0.status, condition: "in [pass, exception]", on_missing: block}
    - {id: PRE-T1-02, evidence_ref: T0.risk_classification.tier, condition: exists, on_missing: block}
    - {id: PRE-T1-03, evidence_ref: T0.value_hypothesis, condition: exists, on_missing: block}
  actors:
    agent: {id: t1-requirements-agent, model_tier: reasoning}
    subagents:
      - {id: functional-analyst, responsibility: "functional and behavioural requirements, persona journeys"}
      - {id: nfr-analyst, responsibility: "performance, availability, scalability, cost NFRs"}
      - {id: autonomy-designer, responsibility: "autonomy level and boundaries per action"}
      - {id: metrics-designer, responsibility: "KPI baseline/target, eval and RAI thresholds"}
      - {id: acceptance-designer, responsibility: "acceptance criteria, failure boundaries, test scenarios"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: product_owner, raci: A}
      - {role: business_owner, raci: R}
      - {role: qa_eval_lead, raci: C}
      - {role: rai_officer, raci: C}
      - {role: solution_architect, raci: C}
  authorities:
    allow: [read:ledger.T0, read:knowledge_base, write:T1.artifacts]
    deny: [write:ledger.T0, write:any_other_terminal]
    data_access: {max_class: internal}
    tool_scopes: [mcp:confluence:read, mcp:sharepoint:read, mcp:jira:read]
    sign_off: {roles: [product_owner, business_owner], min_approvers: 2}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T1-01, ref: playbooks/t1-requirements.md, version: 1.0.0}
      - {id: PB-T1-02, ref: playbooks/autonomy-levels.md, version: 1.0.0}
      - {id: PB-T1-03, ref: playbooks/metric-catalogue.md, version: 1.0.0}
    grounding:
      - {mcp: confluence, scope: "/process-docs, /sops"}
      - {mcp: jira, scope: "related epics"}
  controls:
    automated:
      - {id: CTL-T1-01, rule: "every requirement has id, priority, acceptance_criteria", severity: blocking}
      - {id: CTL-T1-02, rule: "every KPI has numeric baseline and target", severity: blocking}
      - {id: CTL-T1-03, rule: "every eval and RAI threshold is numeric with operator", severity: blocking}
      - {id: CTL-T1-04, rule: "autonomy_level defined for every agent action", severity: blocking}
      - {id: CTL-T1-05, rule: "autonomy_level <= max allowed for risk_tier", severity: blocking}
    checklist:
      ref: checklists/t1.yaml
      items: [CHK-T1-01 requirements traceable to T0 problem, CHK-T1-02 failure boundaries cover out-of-scope and unsafe requests, CHK-T1-03 HITL points defined for irreversible actions, CHK-T1-04 thresholds realistic vs baseline, CHK-T1-05 UX covers error and handoff states]
    tiering:
      high: {min_test_scenarios: 50, rai_thresholds_required: [toxicity, bias, hallucination, pii_leak]}
      medium: {min_test_scenarios: 30, rai_thresholds_required: [toxicity, hallucination, pii_leak]}
      low: {min_test_scenarios: 15, rai_thresholds_required: [toxicity, hallucination]}
  evidence:
    artifacts:
      - {id: functional_requirements, format: table, columns: [req_id, description, priority, persona, acceptance_criteria], required: true}
      - {id: non_functional_requirements, format: table, columns: [nfr_id, category, requirement, target, unit], required: true}
      - {id: behavioural_requirements, format: table, columns: [beh_id, situation, expected_behaviour, prohibited_behaviour], required: true}
      - {id: autonomy_levels, format: table, columns: [action, autonomy_level, hitl_required, boundary], required: true}
      - {id: kpis, format: table, columns: [kpi_id, kpi, baseline, target, unit, measurement_source], required: true}
      - {id: eval_thresholds, format: table, columns: [metric, operator, threshold, dataset_scope], required: true}
      - {id: rai_thresholds, format: table, columns: [metric, operator, threshold, slice], required: true}
      - {id: user_experience, format: table, columns: [journey, step, channel, expected_experience], required: true}
      - {id: acceptance_and_failure, format: table, columns: [scenario_id, scenario, type, expected_outcome], required: true}
    ledger: {key: "${usecase_id}/T1/${run_version}", immutable: true, retention: per_tier}
  outcome_model:
    pass: {route: T2, emits: [eval_thresholds, rai_thresholds, kpis, autonomy_levels]}
    rework: {route_by_root_cause: {requirement: T1, qualification: T0}, requires: [owner_comment]}
    exception: {requires: [waiver_owner, expiry, compensating_control]}
    escalate: {when: "rework_count > 3 or age > escalate_after", route: human_completion}
    terminate: {set_by: business_owner, requires: [reason]}
  timeline:
    expected_duration: {low: 3d, medium: 5d, high: 8d}
    reminder_after: 2d
    escalate_after: 10d
    max_rework_cycles: 3
```

## 6. T2 – Architecture & Design

**Question:** how should the agent operate? The solution architect agent produces the design contract. Each design decision is recorded with an ID so T3 can prove conformance and T9 can assess change impact against it.

**Exit criteria:** approved architecture and design contract, including tool/API contracts and token budget.

```yaml
terminal:
  metadata:
    id: T2
    name: Architecture & Design
    version: 1.0.0
    purpose: How should the agent operate?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T1.pass, T1.exception, T9.reentry.T2, T3.rework.design, T4.rework.design, T5.rework.architecture]
    mode: event
  prerequisites:
    - {id: PRE-T2-01, evidence_ref: T1.status, condition: "in [pass, exception]", on_missing: block}
    - {id: PRE-T2-02, evidence_ref: T1.non_functional_requirements, condition: exists, on_missing: block}
    - {id: PRE-T2-03, evidence_ref: T1.autonomy_levels, condition: exists, on_missing: block}
  actors:
    agent: {id: t2-architect-agent, model_tier: reasoning}
    subagents:
      - {id: system-architect, responsibility: "solution overview, system and deployment architecture"}
      - {id: agent-pattern-designer, responsibility: "agentic pattern, GenAI principles, memory/context strategy"}
      - {id: model-strategist, responsibility: "model selection, routing, fallback, token budget"}
      - {id: contract-designer, responsibility: "tool/API/MCP contracts and A2A interfaces"}
      - {id: data-architect, responsibility: "data strategy: retention, access, compliance"}
      - {id: security-architect, responsibility: "security architecture and threat model draft"}
      - {id: observability-designer, responsibility: "observability, RAI and metric emission design"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: solution_architect, raci: A}
      - {role: engineering_lead, raci: R}
      - {role: security_officer, raci: C}
      - {role: data_owner, raci: C}
      - {role: product_owner, raci: I}
  authorities:
    allow: [read:ledger.T0-T1, read:architecture_repo, read:component_catalogue, write:T2.artifacts]
    deny: [write:ledger.T0-T1, provision:infrastructure]
    data_access: {max_class: internal}
    tool_scopes: [mcp:confluence:read, mcp:sharepoint:read, mcp:arch_repo:read, mcp:mcp_registry:read]
    sign_off: {roles: [solution_architect, security_officer], min_approvers: 2}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T2-01, ref: playbooks/t2-architecture.md, version: 1.0.0}
      - {id: PB-T2-02, ref: playbooks/agentic-patterns.md, version: 1.0.0}
      - {id: PB-T2-03, ref: playbooks/reference-architectures.md, version: 1.0.0}
    grounding:
      - {mcp: arch_repo, scope: "reference architectures, ADRs"}
      - {mcp: mcp_registry, scope: "approved MCP servers and tools"}
      - {mcp: confluence, scope: "/platform-standards"}
  controls:
    automated:
      - {id: CTL-T2-01, rule: "every T1 requirement mapped to >= 1 design decision", severity: blocking}
      - {id: CTL-T2-02, rule: "all tools in approved MCP registry or flagged as new", severity: blocking}
      - {id: CTL-T2-03, rule: "token_budget per task defined and <= T1 cost NFR", severity: blocking}
      - {id: CTL-T2-04, rule: "data classes handled <= T0 data classification approval", severity: blocking}
      - {id: CTL-T2-05, rule: "HITL design covers every action with hitl_required = true", severity: blocking}
    checklist:
      ref: checklists/t2.yaml
      items: [CHK-T2-01 pattern justified vs simpler alternative, CHK-T2-02 model fallback defined, CHK-T2-03 tool contracts have auth and error semantics, CHK-T2-04 memory retention matches data strategy, CHK-T2-05 environments poc/dev/test/prod defined, CHK-T2-06 kill switch designed]
    tiering:
      high: {threat_model: full, architecture_board_review: true}
      medium: {threat_model: standard, architecture_board_review: false}
      low: {threat_model: lightweight, architecture_board_review: false}
  evidence:
    artifacts:
      - {id: solution_overview, format: table, columns: [aspect, description], required: true}
      - {id: system_architecture, format: diagram+table, columns: [component, responsibility, technology, interfaces], required: true}
      - {id: data_strategy, format: table, columns: [data_element, classification, retention, access_policy, residency], required: true}
      - {id: agentic_pattern, format: table, columns: [decision_id, pattern, rationale, genai_principle], required: true}
      - {id: model_strategy, format: table, columns: [use, model, version, fallback, routing_rule], required: true}
      - {id: tool_api_contracts, format: table, columns: [tool_id, mcp_server, operation, auth, input_schema, output_schema, error_semantics], required: true}
      - {id: memory_context_strategy, format: table, columns: [memory_type, store, scope, ttl], required: true}
      - {id: hitl_design, format: table, columns: [action, trigger, approver_role, timeout_behaviour], required: true}
      - {id: token_budget, format: table, columns: [task, max_tokens, max_cost, on_exceed], required: true}
      - {id: security_architecture, format: table, columns: [threat, control, layer], required: true}
      - {id: observability_design, format: table, columns: [signal, source, metric, sink, alert], required: true}
      - {id: rai_metric_emission, format: table, columns: [rai_metric, emission_point, frequency], required: true}
      - {id: deployment_architecture, format: table, columns: [environment, purpose, infra, data_allowed], required: true}
      - {id: design_decisions, format: table, columns: [decision_id, decision, req_ids, status], required: true}
    ledger: {key: "${usecase_id}/T2/${run_version}", immutable: true, retention: per_tier}
  outcome_model:
    pass: {route: T3, emits: [design_decisions, tool_api_contracts, token_budget]}
    rework: {route_by_root_cause: {design: T2, requirement: T1}, requires: [owner_comment]}
    exception: {requires: [waiver_owner, expiry, compensating_control]}
    escalate: {when: "rework_count > 3 or age > escalate_after", route: human_completion}
    terminate: {set_by: business_owner, requires: [reason]}
  timeline:
    expected_duration: {low: 4d, medium: 7d, high: 12d}
    reminder_after: 3d
    escalate_after: 15d
    max_rework_cycles: 3
```

## 7. T3 – Build & Integration

**Question:** can we construct the agent reproducibly? The builder agent works in a repository through a coding harness, opens pull requests and never merges its own work. Its output is an immutable, hash-identified candidate package that T4, T5, T6 and T7 all bind to.

**Exit criteria:** deployable candidate (package hash) + engineering evidence.

```yaml
terminal:
  metadata:
    id: T3
    name: Build & Integration
    version: 1.0.0
    purpose: Can we construct the agent reproducibly?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T2.pass, T2.exception, T9.reentry.T3, T4.rework.implementation, T5.rework.control_missing, T7.rollback]
    mode: event
  prerequisites:
    - {id: PRE-T3-01, evidence_ref: T2.status, condition: "in [pass, exception]", on_missing: block}
    - {id: PRE-T3-02, evidence_ref: T2.tool_api_contracts, condition: exists, on_missing: block}
    - {id: PRE-T3-03, evidence_ref: env.dev, condition: provisioned, on_missing: block}
    - {id: PRE-T3-04, evidence_ref: template.version, condition: pinned, on_missing: block}
  actors:
    agent: {id: t3-builder-agent, model_tier: coding}
    subagents:
      - {id: scaffolder, responsibility: "repo and infra from golden template (IaC)"}
      - {id: agent-implementer, responsibility: "agent graph and orchestration code"}
      - {id: prompt-engineer, responsibility: "versioned prompts and instructions in prompt registry"}
      - {id: tool-integrator, responsibility: "tool wrappers, MCP bindings, A2A interfaces"}
      - {id: memory-rag-builder, responsibility: "context store and retrieval pipeline"}
      - {id: harness-integrator, responsibility: "harness, eval hooks, tracing, metric and RAI emission"}
      - {id: pipeline-builder, responsibility: "CI/CD with tests, scans, packaging"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: engineering_lead, raci: A}
      - {role: sre, raci: R}
      - {role: solution_architect, raci: C}
      - {role: qa_eval_lead, raci: I}
  authorities:
    allow: [read:ledger.T0-T2, write:repo.feature_branch, open:pull_request, run:ci_pipeline, provision:dev_env]
    deny: [merge:main, write:secrets, deploy:test, deploy:prod, write:T1.thresholds]
    data_access: {max_class: synthetic_or_masked}
    tool_scopes: [mcp:git:branch_write, mcp:ci:run, mcp:prompt_registry:write, mcp:artifact_store:write]
    sign_off: {roles: [engineering_lead], min_approvers: 1, plus: "solution_architect if any design deviation"}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T3-01, ref: playbooks/t3-build.md, version: 1.0.0}
      - {id: PB-T3-02, ref: playbooks/golden-template.md, version: 1.0.0}
      - {id: PB-T3-03, ref: playbooks/prompt-versioning.md, version: 1.0.0}
    grounding:
      - {mcp: git, scope: "component catalogue, prior agents"}
      - {mcp: confluence, scope: "/engineering-standards"}
      - {mcp: mcp_registry, scope: "approved servers"}
  controls:
    automated:
      - {id: CTL-T3-01, rule: "ci.status == green", severity: blocking}
      - {id: CTL-T3-02, rule: "unit_coverage >= 80%", severity: blocking}
      - {id: CTL-T3-03, rule: "sast.critical == 0 and sast.high == 0", severity: blocking}
      - {id: CTL-T3-04, rule: "secret_scan.findings == 0", severity: blocking}
      - {id: CTL-T3-05, rule: "every req_id traced to >= 1 test_id", severity: blocking}
      - {id: CTL-T3-06, rule: "telemetry.traces and rai_metrics emitting in dev", severity: blocking}
      - {id: CTL-T3-07, rule: "all prompts and tools have registry version", severity: blocking}
      - {id: CTL-T3-08, rule: "sbom generated and licences approved", severity: advisory}
    checklist:
      ref: checklists/t3.yaml
      items: [CHK-T3-01 build reproducible from manifest, CHK-T3-02 design deviations documented and approved, CHK-T3-03 token budget enforced in code, CHK-T3-04 kill switch implemented, CHK-T3-05 HITL hooks implemented per T2, CHK-T3-06 change log complete]
  evidence:
    artifacts:
      - {id: build_manifest, format: table, columns: [item, name, version, hash], required: true}
      - {id: traceability_matrix, format: table, columns: [req_id, component, prompt_id, tool_id, test_id], required: true}
      - {id: design_conformance, format: table, columns: [decision_id, implemented, deviation, approver], required: true}
      - {id: test_results, format: table, columns: [suite, total, passed, failed, coverage], required: true}
      - {id: security_build_checks, format: table, columns: [scan, tool, critical, high, medium, status], required: true}
      - {id: observability_check, format: table, columns: [signal, emitting, sample_trace_id], required: true}
      - {id: config_register, format: table, columns: [config_key, environment, value_ref, autonomy_related], required: true}
      - {id: change_log, format: table, columns: [change_id, description, req_id, pr_link], required: true}
      - {id: candidate_package, format: reference, columns: [package_uri, sha256], required: true}
    ledger: {key: "${usecase_id}/T3/${run_version}", immutable: true, retention: per_tier}
  outcome_model:
    pass: {route: T4, emits: [candidate_package.sha256, build_manifest]}
    rework: {route_by_root_cause: {implementation: T3, design: T2}, requires: [owner_comment]}
    exception: {requires: [waiver_owner, expiry, compensating_control], recheck_at: T6}
    escalate: {when: "rework_count > 3 or age > escalate_after", route: human_completion}
    terminate: {set_by: business_owner, requires: [reason]}
  timeline:
    expected_duration: {low: 5d, medium: 10d, high: 15d}
    reminder_after: 5d
    escalate_after: 20d
    max_rework_cycles: 3
```

## 8. T4 – Evaluation

**Question:** does the agent behave as designed? The evaluation agent runs the T3 candidate against T1 thresholds. It is denied write access to both the candidate and the thresholds, which is what makes its evidence independent. It also freezes the regression pack that T8 and T9 reuse.

**Exit criteria:** evaluation evidence + pass/remediation disposition; regression pack frozen.

```yaml
terminal:
  metadata:
    id: T4
    name: Evaluation
    version: 1.0.0
    purpose: Does the agent behave as designed?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T3.pass, T3.exception, T9.reentry.T4]
    mode: event
  prerequisites:
    - {id: PRE-T4-01, evidence_ref: T3.candidate_package.sha256, condition: exists, on_missing: block}
    - {id: PRE-T4-02, evidence_ref: T1.eval_thresholds, condition: exists, on_missing: block}
    - {id: PRE-T4-03, evidence_ref: T1.rai_thresholds, condition: exists, on_missing: block}
    - {id: PRE-T4-04, evidence_ref: env.test, condition: "deployed_hash == T3.candidate_package.sha256", on_missing: block}
    - {id: PRE-T4-05, evidence_ref: dataset.golden.approval, condition: "approved by data_owner", on_missing: block}
  actors:
    agent: {id: t4-evaluation-agent, model_tier: reasoning}
    subagents:
      - {id: dataset-curator, responsibility: "golden set: synthetic from T1 scenarios + approved real-world samples"}
      - {id: test-runner, responsibility: "functional, regression, multi-turn and trajectory tests"}
      - {id: judge, responsibility: "LLM-as-judge and deterministic scorers"}
      - {id: failure-mode-tester, responsibility: "T1 failure boundaries, tool failures, out-of-scope"}
      - {id: cost-latency-profiler, responsibility: "tokens, cost per task, p50/p95 latency"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: qa_eval_lead, raci: A}
      - {role: product_owner, raci: R}
      - {role: data_owner, raci: C}
      - {role: engineering_lead, raci: I}
  authorities:
    allow: [read:ledger.T0-T3, invoke:test_env_agent, write:eval_store, write:T4.artifacts]
    deny: [write:repo, write:candidate_package, write:T1.thresholds, deploy:any]
    data_access: {max_class: confidential_masked}
    tool_scopes: [mcp:harness:run, mcp:eval_store:write, mcp:dataset_registry:read]
    sign_off: {roles: [qa_eval_lead, product_owner], min_approvers: 2}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T4-01, ref: playbooks/t4-evaluation.md, version: 1.0.0}
      - {id: PB-T4-02, ref: playbooks/golden-dataset.md, version: 1.0.0}
      - {id: PB-T4-03, ref: playbooks/judge-calibration.md, version: 1.0.0}
    grounding:
      - {mcp: dataset_registry, scope: "approved datasets"}
      - {mcp: eval_store, scope: "prior eval runs for this use case"}
  controls:
    automated:
      - {id: CTL-T4-01, rule: "each metric in T1.eval_thresholds meets operator and threshold", severity: blocking}
      - {id: CTL-T4-02, rule: "each metric in T1.rai_thresholds meets operator and threshold", severity: blocking}
      - {id: CTL-T4-03, rule: "every req_id has >= 1 executed case", severity: blocking}
      - {id: CTL-T4-04, rule: "open_defects.critical == 0", severity: blocking}
      - {id: CTL-T4-05, rule: "judge_human_agreement >= 0.85", severity: blocking}
      - {id: CTL-T4-06, rule: "cost_per_task <= T2.token_budget.max_cost", severity: blocking}
      - {id: CTL-T4-07, rule: "p95_latency <= T1 latency NFR", severity: blocking}
      - {id: CTL-T4-08, rule: "failure-mode safe_fail_rate == 100%", severity: blocking}
    checklist:
      ref: checklists/t4.yaml
      items: [CHK-T4-01 dataset provenance recorded, CHK-T4-02 synthetic vs real split justified, CHK-T4-03 defects assigned a root_cause_terminal, CHK-T4-04 regression pack frozen and versioned, CHK-T4-05 results bound to candidate hash]
    tiering:
      high: {min_cases: 500, human_label_slice: 200, adversarial: full}
      medium: {min_cases: 250, human_label_slice: 100, adversarial: standard}
      low: {min_cases: 100, human_label_slice: 50, adversarial: smoke}
  evidence:
    artifacts:
      - {id: golden_dataset_register, format: table, columns: [dataset_id, version, size, synthetic_pct, real_pct, approver], required: true}
      - {id: test_case_results, format: table, columns: [case_id, req_id, expected, actual, score, result], required: true}
      - {id: quality_vs_threshold, format: table, columns: [metric, threshold, actual, result], required: true}
      - {id: rai_vs_threshold, format: table, columns: [metric, slice, threshold, actual, result], required: true}
      - {id: cost_latency, format: table, columns: [measure, budget, actual, result], required: true}
      - {id: failure_mode_results, format: table, columns: [scenario_id, scenario, observed, safe_fail], required: true}
      - {id: defect_log, format: table, columns: [defect_id, severity, root_cause_terminal, status], required: true}
      - {id: judge_calibration, format: table, columns: [judge, sample_size, agreement], required: true}
      - {id: regression_pack, format: reference, columns: [pack_id, version, case_count], required: true}
    ledger: {key: "${usecase_id}/T4/${run_version}", immutable: true, bound_to: T3.candidate_package.sha256, retention: per_tier}
  outcome_model:
    pass: {route: T5, emits: [regression_pack, eval_baseline]}
    rework: {route_by_root_cause: {implementation: T3, design: T2, requirement: T1}, requires: [defect_log]}
    exception: {when: "only advisory or non-critical threshold missed", requires: [waiver_owner, expiry, compensating_control], recheck_at: [T6, T8]}
    escalate: {when: "rework_count > 3 or judge dispute", route: human_completion}
    terminate: {set_by: business_owner, requires: [reason]}
  timeline:
    expected_duration: {low: 4d, medium: 7d, high: 12d}
    reminder_after: 3d
    escalate_after: 15d
    max_rework_cycles: 3
```

## 9. T5 – Trust, Risk & Assurance

**Question:** is the agentic system safe and compliant to release? Depth scales with the T0 risk tier through the `tiering` block, so one spec serves a low-risk internal assistant and a regulated autonomous agent. Residual risk can only be accepted by the business `risk_owner`, never by an agent.

**Exit criteria:** assurance attestation + accepted residual risk register.

```yaml
terminal:
  metadata:
    id: T5
    name: Trust, Risk & Assurance
    version: 1.0.0
    purpose: Is the agentic system safe and compliant for release?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T4.pass, T4.exception, T9.reentry.T5, T8.event.safety_breach]
    mode: event
  prerequisites:
    - {id: PRE-T5-01, evidence_ref: T4.status, condition: "in [pass, exception]", on_missing: block}
    - {id: PRE-T5-02, evidence_ref: T4.rai_vs_threshold, condition: exists, on_missing: block}
    - {id: PRE-T5-03, evidence_ref: T2.security_architecture, condition: exists, on_missing: block}
    - {id: PRE-T5-04, evidence_ref: T2.data_strategy, condition: exists, on_missing: block}
    - {id: PRE-T5-05, evidence_ref: env.test, condition: "deployed_hash == T3.candidate_package.sha256", on_missing: block}
  actors:
    agent: {id: t5-assurance-agent, model_tier: reasoning}
    subagents:
      - {id: security-tester, responsibility: "prompt injection (direct/indirect), jailbreak, tool abuse, exfiltration; OWASP LLM Top 10"}
      - {id: access-verifier, responsibility: "agent identity least privilege, tool scopes, secrets, user authz passthrough"}
      - {id: privacy-assessor, responsibility: "PII/PHI in prompts, logs, memory, outputs; retention and residency"}
      - {id: regulatory-mapper, responsibility: "map controls to applicable regulations and internal policy"}
      - {id: rai-assurer, responsibility: "RAI evidence, transparency, human oversight, contestability"}
      - {id: resilience-tester, responsibility: "safe-fail, fallback to human, kill switch, degradation"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: security_officer, raci: A}
      - {role: privacy_officer, raci: R}
      - {role: rai_officer, raci: R}
      - {role: compliance_officer, raci: R}
      - {role: risk_owner, raci: A, scope: residual_risk_acceptance}
  authorities:
    allow: [read:ledger.T0-T4, invoke:test_env_agent, run:security_tests, write:T5.artifacts]
    deny: [write:repo, write:candidate_package, accept:residual_risk, deploy:any]
    data_access: {max_class: confidential_masked}
    tool_scopes: [mcp:redteam_harness:run, mcp:iam:read, mcp:dlp_scanner:run, mcp:control_library:read, mcp:grc:write]
    sign_off:
      low: {roles: [security_officer], min_approvers: 1}
      medium: {roles: [security_officer, privacy_officer], min_approvers: 2}
      high: {roles: [security_officer, privacy_officer, rai_officer, compliance_officer], min_approvers: 4, board: rai_board}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T5-01, ref: playbooks/t5-assurance.md, version: 1.0.0}
      - {id: PB-T5-02, ref: playbooks/llm-red-team.md, version: 1.0.0}
      - {id: PB-T5-03, ref: playbooks/privacy-impact-assessment.md, version: 1.0.0}
      - {id: PB-T5-04, ref: playbooks/regulatory-mapping.md, version: 1.0.0}
    grounding:
      - {mcp: control_library, scope: "security and RAI controls"}
      - {mcp: sharepoint, scope: "/policies/security, /policies/privacy, /policies/rai"}
      - {mcp: grc, scope: "prior assurance reports"}
  controls:
    automated:
      - {id: CTL-T5-01, rule: "injection_success_rate <= tier.max_injection_success", severity: blocking}
      - {id: CTL-T5-02, rule: "jailbreak_success_rate <= tier.max_jailbreak_success", severity: blocking}
      - {id: CTL-T5-03, rule: "pii_leak_findings == 0", severity: blocking}
      - {id: CTL-T5-04, rule: "agent identity permissions subset of T2 design", severity: blocking}
      - {id: CTL-T5-05, rule: "kill_switch_test == pass", severity: blocking}
      - {id: CTL-T5-06, rule: "findings.critical.unmitigated == 0", severity: blocking}
      - {id: CTL-T5-07, rule: "every residual risk has risk_owner and decision", severity: blocking}
    checklist:
      ref: checklists/t5.yaml
      items: [CHK-T5-01 threat model updated from T2 draft, CHK-T5-02 regulatory map complete for tier, CHK-T5-03 disclosure to users meets policy, CHK-T5-04 human override path tested, CHK-T5-05 logs exclude secrets and raw PII]
    tiering:
      high: {red_team: full_manual_plus_automated, max_injection_success: 0.01, max_jailbreak_success: 0.01, pia: full}
      medium: {red_team: automated_plus_sample_manual, max_injection_success: 0.02, max_jailbreak_success: 0.02, pia: standard}
      low: {red_team: automated_smoke, max_injection_success: 0.05, max_jailbreak_success: 0.05, pia: screening}
  evidence:
    artifacts:
      - {id: threat_model_results, format: table, columns: [threat_id, threat, test, result, residual_risk], required: true}
      - {id: security_control_evidence, format: table, columns: [control_id, implemented, evidence_link], required: true}
      - {id: access_control_matrix, format: table, columns: [identity, resource, permission, justification], required: true}
      - {id: privacy_assessment, format: table, columns: [data_element, class, masking, retention, lawful_basis], required: true}
      - {id: regulatory_map, format: table, columns: [regulation, clause, control_id, status], required: true}
      - {id: rai_assurance, format: table, columns: [rai_metric, T4_actual, threshold, accepted], required: true}
      - {id: resilience_verification, format: table, columns: [scenario, expected_fallback, observed, result], required: true}
      - {id: residual_risk_register, format: table, columns: [risk_id, risk, rating, risk_owner, decision, review_date], required: true}
      - {id: assurance_attestation, format: signed_record, columns: [role, decision, date], required: true}
    ledger: {key: "${usecase_id}/T5/${run_version}", immutable: true, bound_to: T3.candidate_package.sha256, retention: per_tier}
  outcome_model:
    pass: {route: T6, emits: [assurance_attestation, residual_risk_register]}
    rework: {route_by_root_cause: {control_missing: T3, architecture: T2}, requires: [findings]}
    exception: {set_by: risk_owner, requires: [risk_acceptance, expiry, compensating_control], recheck_at: [T6, T8]}
    escalate: {when: "rework_count > 3 or assurance functions disagree", route: rai_board}
    terminate: {set_by: [business_owner, security_officer], when: "unacceptable residual risk", requires: [reason]}
  timeline:
    expected_duration: {low: 3d, medium: 8d, high: 15d}
    reminder_after: 3d
    escalate_after: 20d
    max_rework_cycles: 3
```

## 10. T6 – Release Readiness

**Question:** is everything in place for production? T6 is an aggregator and verifier: it proves the evidence chain T0–T5 is complete, no waiver has expired, and the package being released is byte-identical to the one evaluated and assured. It then assembles what operations needs.

**Exit criteria:** release authorisation (signed go decision + change record).

```yaml
terminal:
  metadata:
    id: T6
    name: Release Readiness
    version: 1.0.0
    purpose: Is everything necessary for production ready?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T5.pass, T5.exception, T9.reentry.T6]
    mode: event
  prerequisites:
    - {id: PRE-T6-01, evidence_ref: "T0..T5.status", condition: "all in [pass, exception]", on_missing: block}
    - {id: PRE-T6-02, evidence_ref: T5.assurance_attestation, condition: signed, on_missing: block}
    - {id: PRE-T6-03, evidence_ref: change.window, condition: requested, on_missing: warn}
  actors:
    agent: {id: t6-readiness-agent, model_tier: standard}
    subagents:
      - {id: evidence-auditor, responsibility: "chain completeness, waiver expiry, hash consistency"}
      - {id: runbook-author, responsibility: "runbook, kill-switch procedure, triage steps"}
      - {id: rollout-planner, responsibility: "shadow/canary/full plan and rollback strategy"}
      - {id: ops-readiness-checker, responsibility: "ownership, on-call, support KB, T8 dashboards and alerts"}
      - {id: change-coordinator, responsibility: "change record in ITSM"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: release_manager, raci: A}
      - {role: service_owner, raci: R}
      - {role: sre, raci: R}
      - {role: business_owner, raci: A, scope: go_no_go}
  authorities:
    allow: [read:ledger.T0-T5, write:runbook_repo, create:change_request, configure:monitoring_dev, write:T6.artifacts]
    deny: [deploy:prod, approve:change_request, write:candidate_package]
    data_access: {max_class: internal}
    tool_scopes: [mcp:servicenow:change_create, mcp:cmdb:read, mcp:monitoring:configure, mcp:confluence:write]
    sign_off: {roles: [release_manager, service_owner, business_owner], min_approvers: 3, external: "CAB where change policy requires"}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T6-01, ref: playbooks/t6-release-readiness.md, version: 1.0.0}
      - {id: PB-T6-02, ref: playbooks/runbook-template.md, version: 1.0.0}
      - {id: PB-T6-03, ref: playbooks/progressive-rollout.md, version: 1.0.0}
    grounding:
      - {mcp: servicenow, scope: "change policy, support groups"}
      - {mcp: confluence, scope: "/runbooks"}
  controls:
    automated:
      - {id: CTL-T6-01, rule: "all prior terminal statuses in [pass, exception]", severity: blocking}
      - {id: CTL-T6-02, rule: "no waiver with expiry < release_date", severity: blocking}
      - {id: CTL-T6-03, rule: "T4.bound_to == T5.bound_to == release.package_sha256", severity: blocking}
      - {id: CTL-T6-04, rule: "rollback_tested == true", severity: blocking}
      - {id: CTL-T6-05, rule: "on_call rota and service_owner assigned", severity: blocking}
      - {id: CTL-T6-06, rule: "T8 alerts configured for every T1 KPI and T2 observability signal", severity: blocking}
      - {id: CTL-T6-07, rule: "change_request.status == approved", severity: blocking}
    checklist:
      ref: checklists/t6.yaml
      items: [CHK-T6-01 runbook covers known failure modes from T4, CHK-T6-02 rollout stages have success criteria, CHK-T6-03 support KB and user comms ready, CHK-T6-04 agent registered in agent registry as pending]
    tiering:
      high: {rollout: [shadow, canary, full], cab_required: true}
      medium: {rollout: [canary, full], cab_required: true}
      low: {rollout: [full], cab_required: false}
  evidence:
    artifacts:
      - {id: gate_evidence_summary, format: table, columns: [terminal, status, signed_by, date, open_waivers, waiver_expiry], required: true}
      - {id: deployment_package, format: table, columns: [item, version, sha256, environment_config_ref], required: true}
      - {id: runbook, format: document, columns: [section, owner], required: true}
      - {id: rollback_strategy, format: table, columns: [trigger_condition, steps, data_memory_rollback, tested], required: true}
      - {id: rollout_plan, format: table, columns: [stage, traffic_pct, soak_period, success_criteria], required: true}
      - {id: operational_ownership, format: table, columns: [function, team, contact, escalation], required: true}
      - {id: support_readiness, format: table, columns: [item, status, link], required: true}
      - {id: monitoring_readiness, format: table, columns: [signal, dashboard, alert_threshold, routed_to], required: true}
      - {id: release_authorisation, format: signed_record, columns: [role, decision, date, change_id], required: true}
    ledger: {key: "${usecase_id}/T6/${run_version}", immutable: true, bound_to: T3.candidate_package.sha256, retention: per_tier}
  outcome_model:
    pass: {route: T7, emits: [release_authorisation, rollout_plan, deployment_package]}
    rework: {route_by_root_cause: {missing_evidence: owning_terminal, ops_gap: T6}, requires: [gap_list]}
    exception: {when: "go with conditions", requires: [conditions, expiry], example: "limited rollout cap"}
    escalate: {when: "go/no-go dispute or rework_count > 3", route: business_owner_and_release_board}
    terminate: {set_by: business_owner, requires: [reason]}
  timeline:
    expected_duration: {low: 2d, medium: 3d, high: 5d}
    reminder_after: 1d
    escalate_after: 7d
    max_rework_cycles: 3
```

## 11. T7 – Deployment & Transition

**Question:** is the approved system deployed safely and handed over to operations? The deployment agent is the highest-privilege agent in the lifecycle, so its authority is the narrowest: it may only run the pipeline with the authorised package hash, inside the approved change window. Stage advances are policy checks on live metrics; a human approves full rollout. Any blocking breach triggers automatic rollback.

**Exit criteria:** operational system in production, registered, and accepted by BAU support.

```yaml
terminal:
  metadata:
    id: T7
    name: Deployment & Transition
    version: 1.0.0
    purpose: Can the approved agentic system be safely deployed and handed over?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T6.pass, T6.exception]
    mode: event
    window: "${T6.release_authorisation.change_id}.window"
  prerequisites:
    - {id: PRE-T7-01, evidence_ref: T6.release_authorisation, condition: signed, on_missing: block}
    - {id: PRE-T7-02, evidence_ref: change.window, condition: "now within window", on_missing: block}
    - {id: PRE-T7-03, evidence_ref: T6.deployment_package.sha256, condition: "== T3.candidate_package.sha256", on_missing: block}
  actors:
    agent: {id: t7-deployment-agent, model_tier: standard}
    subagents:
      - {id: env-verifier, responsibility: "environment, config, secrets references, model and tool endpoints"}
      - {id: rollout-controller, responsibility: "execute shadow/canary/full per T6 rollout plan"}
      - {id: smoke-validator, responsibility: "run smoke subset of T4 regression pack in prod"}
      - {id: hypercare-monitor, responsibility: "elevated monitoring and incident triage during hypercare"}
      - {id: registrar, responsibility: "agent registry and CMDB entries"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: release_manager, raci: A}
      - {role: sre, raci: R}
      - {role: service_owner, raci: A, scope: handover_acceptance}
      - {role: business_owner, raci: I}
  authorities:
    allow: [run:cd_pipeline.with_hash_only, set:traffic_split, trigger:rollback, write:agent_registry, write:cmdb, write:T7.artifacts]
    deny: [write:repo, write:config, write:secrets, deploy:unauthorised_hash, deploy:outside_window, promote:100pct_without_approval]
    data_access: {max_class: per_T2_prod_design}
    tool_scopes: [mcp:cd:deploy, mcp:traffic_manager:write, mcp:monitoring:read, mcp:agent_registry:write, mcp:cmdb:write, mcp:servicenow:incident_create]
    sign_off: {roles: [release_manager, service_owner], min_approvers: 2, stage_approval: {full_rollout: service_owner}}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate, rework_on_auto_rollback]}
  playbooks:
    procedures:
      - {id: PB-T7-01, ref: playbooks/t7-deployment.md, version: 1.0.0}
      - {id: PB-T7-02, ref: playbooks/rollback.md, version: 1.0.0}
      - {id: PB-T7-03, ref: playbooks/hypercare-handover.md, version: 1.0.0}
    grounding:
      - {mcp: confluence, scope: "${T6.runbook}"}
  controls:
    automated:
      - {id: CTL-T7-01, rule: "deployed_hash == T6.deployment_package.sha256", severity: blocking}
      - {id: CTL-T7-02, rule: "env_verification.all_green", severity: blocking}
      - {id: CTL-T7-03, rule: "shadow quality within T4 baseline tolerance", severity: blocking, applies: [high]}
      - {id: CTL-T7-04, rule: "no alert breach during canary soak", severity: blocking, applies: [high, medium]}
      - {id: CTL-T7-05, rule: "smoke_pass_rate == 100%", severity: blocking}
      - {id: CTL-T7-06, rule: "agent registered with owner, autonomy_level, version", severity: blocking}
      - {id: CTL-T7-07, rule: "hypercare: no open sev1/sev2 at exit", severity: blocking}
    auto_rollback_on: [CTL-T7-01, CTL-T7-03, CTL-T7-04, CTL-T7-05]
    checklist:
      ref: checklists/t7.yaml
      items: [CHK-T7-01 deployment log complete per stage, CHK-T7-02 rollback executed cleanly if triggered, CHK-T7-03 support team accepted handover, CHK-T7-04 hypercare incidents closed or transferred]
    tiering:
      high: {canary_pct: 5, soak: 72h, hypercare: 14d}
      medium: {canary_pct: 10, soak: 24h, hypercare: 7d}
      low: {canary_pct: null, soak: 4h, hypercare: 3d}
  evidence:
    artifacts:
      - {id: deployment_log, format: table, columns: [stage, start, end, traffic_pct, result], required: true}
      - {id: env_config_verification, format: table, columns: [check, expected, actual, result], required: true}
      - {id: stage_metrics, format: table, columns: [stage, metric, threshold, actual, result], required: true}
      - {id: smoke_results, format: table, columns: [case_id, result], required: true}
      - {id: hypercare_log, format: table, columns: [incident_id, severity, opened, closed, resolution], required: true}
      - {id: registry_entry, format: reference, columns: [agent_id, version, owner, autonomy_level], required: true}
      - {id: handover_acceptance, format: signed_record, columns: [role, decision, date], required: true}
    ledger: {key: "${usecase_id}/T7/${run_version}", immutable: true, bound_to: T3.candidate_package.sha256, retention: per_tier}
  outcome_model:
    pass: {route: T8, emits: [registry_entry, prod_version]}
    rework: {on: auto_rollback, route_by_root_cause: {defect: T3, readiness_gap: T6, environment: T7}, requires: [rollback_report]}
    exception: {not_allowed: true}
    escalate: {when: "rollback fails or sev1/sev2 incident", route: [sre_incident_bridge, service_owner]}
    terminate: {set_by: business_owner, requires: [reason], then: T9.retire}
  timeline:
    expected_duration: {low: 1d+3d_hypercare, medium: 2d+7d_hypercare, high: 5d+14d_hypercare}
    reminder_after: 1d
    escalate_after: window_end
    max_rework_cycles: 2
```

## 12. T8 – Operate & Observe

**Question:** is the system operating as expected, and can we trace its operational and business impact? T8 runs continuously, so its YAML adds two things the others lack: `monitors` (real-time signals with thresholds and the event each breach raises) and a periodic `review` that receives an outcome status like any other terminal. Events route to T5, T7 rollback or T9.

**Exit criteria (per review cycle):** operating health attested; change triggers raised to T9 where needed.

```yaml
terminal:
  metadata:
    id: T8
    name: Operate & Observe
    version: 1.0.0
    purpose: Is the system operating as expected and can we trace its impact?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T7.pass]
    mode: continuous
    review_schedule: {high: "weekly", medium: "fortnightly", low: "monthly"}
  prerequisites:
    - {id: PRE-T8-01, evidence_ref: T7.registry_entry, condition: "status == live", on_missing: block}
    - {id: PRE-T8-02, evidence_ref: T6.monitoring_readiness, condition: exists, on_missing: block}
    - {id: PRE-T8-03, evidence_ref: T4.regression_pack, condition: frozen, on_missing: block}
  actors:
    agent: {id: t8-operations-agent, model_tier: standard}
    subagents:
      - {id: trace-analyst, responsibility: "trajectory anomalies, loops, abandoned tasks"}
      - {id: tool-behaviour-monitor, responsibility: "tool success, latency, unexpected tools, autonomy breaches"}
      - {id: cost-monitor, responsibility: "tokens and cost per task vs budget, quotas"}
      - {id: reliability-monitor, responsibility: "availability, error rate, p95 latency vs SLA"}
      - {id: drift-evaluator, responsibility: "online evals on sampled traffic, scheduled regression replay"}
      - {id: safety-monitor, responsibility: "injection attempts, policy violations, PII leakage, RAI metrics"}
      - {id: kpi-analyst, responsibility: "business KPIs vs T1 targets, value vs T0 hypothesis"}
      - {id: feedback-analyst, responsibility: "ratings, complaints, override and escalation rates"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: service_owner, raci: A}
      - {role: sre, raci: R}
      - {role: product_owner, raci: R, scope: kpis}
      - {role: rai_officer, raci: C, scope: safety_signals}
  authorities:
    allow: [read:telemetry, read:traces_masked, run:online_eval, create:incident, raise:lifecycle_event, write:T8.artifacts]
    deny: [write:repo, write:config, deploy:any]
    emergency: {allow: [reduce:autonomy_level, activate:kill_switch], when: "safety monitor breach severity == critical", notify: [service_owner, security_officer]}
    data_access: {max_class: confidential_masked}
    tool_scopes: [mcp:observability:read, mcp:eval_store:write, mcp:servicenow:incident_create, mcp:feedback:read, mcp:kill_switch:invoke]
    sign_off: {roles: [service_owner], min_approvers: 1, applies_to: periodic_review}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception], orchestrator: [escalate], agent: [raise_event]}
  playbooks:
    procedures:
      - {id: PB-T8-01, ref: playbooks/t8-operations.md, version: 1.0.0}
      - {id: PB-T8-02, ref: playbooks/incident-response-agents.md, version: 1.0.0}
      - {id: PB-T8-03, ref: playbooks/drift-detection.md, version: 1.0.0}
    grounding:
      - {mcp: observability, scope: "traces, metrics, logs"}
      - {mcp: servicenow, scope: "incidents and problems for this agent"}
  monitors:
    - {id: MON-01, signal: safety.policy_violation_rate, threshold: "> T1.rai_thresholds", raises: event.safety_breach}
    - {id: MON-02, signal: safety.pii_leak, threshold: "> 0", raises: event.safety_breach}
    - {id: MON-03, signal: reliability.availability, threshold: "< T1 SLA", raises: event.incident}
    - {id: MON-04, signal: eval.online_score, threshold: "< T4.eval_baseline - tolerance", raises: event.drift}
    - {id: MON-05, signal: cost.per_task, threshold: "> T2.token_budget.max_cost for 7d", raises: event.cost_overrun}
    - {id: MON-06, signal: kpi.value, threshold: "< T1.kpis.target for N reviews", raises: event.kpi_shortfall}
    - {id: MON-07, signal: autonomy.boundary_breach, threshold: "> 0", raises: event.safety_breach}
    - {id: MON-08, signal: upstream.deprecation, threshold: "model or tool deprecation notice", raises: event.upstream_change}
    - {id: MON-09, signal: waiver.expiry, threshold: "expiry within 14d", raises: event.waiver_expiring}
  controls:
    automated:
      - {id: CTL-T8-01, rule: "all monitors reporting (no silent signals)", severity: blocking}
      - {id: CTL-T8-02, rule: "regression replay pass_rate >= T4 baseline - tolerance", severity: blocking}
      - {id: CTL-T8-03, rule: "no open sev1/sev2 older than SLA", severity: blocking}
      - {id: CTL-T8-04, rule: "no expired waivers", severity: blocking}
    checklist:
      ref: checklists/t8.yaml
      items: [CHK-T8-01 KPI trend explained, CHK-T8-02 incidents have root cause, CHK-T8-03 feedback themes actioned or raised to T9, CHK-T8-04 drift analysis covers all eval slices]
  evidence:
    artifacts:
      - {id: operating_health_report, format: table, columns: [metric, threshold, actual, trend, status], required: true}
      - {id: incident_problem_log, format: table, columns: [id, severity, opened, closed, root_cause, linked_event], required: true}
      - {id: drift_report, format: table, columns: [metric, slice, baseline, current, delta], required: true}
      - {id: cost_report, format: table, columns: [period, tasks, tokens, cost, budget], required: true}
      - {id: kpi_scorecard, format: table, columns: [kpi_id, baseline, target, actual, value_realised], required: true}
      - {id: feedback_themes, format: table, columns: [theme, volume, sentiment, action], required: true}
      - {id: raised_events, format: table, columns: [event_id, type, raised_at, routed_to, status], required: true}
    ledger: {key: "${usecase_id}/T8/${review_period}", immutable: true, retention: per_tier}
  outcome_model:
    pass: {route: T8.continue}
    rework: {route: T8, when: "review artifacts incomplete"}
    exception: {when: "known issue tolerated", requires: [waiver_owner, expiry]}
    escalate: {when: "critical safety breach or repeated sev1", route: [service_owner, security_officer, rai_officer]}
    terminate: {set_by: business_owner, route: T9.retire}
    event_routes:
      event.safety_breach: {immediate: [reduce_autonomy_or_kill_switch], then: T5}
      event.incident: {route: itsm, if_sev1: T7.rollback}
      event.drift: {route: T9}
      event.cost_overrun: {route: T9}
      event.kpi_shortfall: {route: T9, notify: business_owner}
      event.upstream_change: {route: T9}
      event.waiver_expiring: {route: owning_terminal_owner}
  timeline:
    expected_duration: continuous
    review_due: per review_schedule
    reminder_after: 2d_past_review_due
    escalate_after: 7d_past_review_due
    max_rework_cycles: 3
```

## 13. T9 – Evolve / Retire

**Question:** how do we continuously improve, or retire, the system? T9 is a router: it classifies each change and sends it back into the lifecycle at the shallowest terminal that is still safe, so small changes stay fast and large ones stay governed. Its YAML therefore carries a `change_classes` block that the orchestrator uses for re-entry, plus a retirement procedure.

**Exit criteria:** approved change routed into the lifecycle, or retirement closure report.

```yaml
terminal:
  metadata:
    id: T9
    name: Evolve / Retire
    version: 1.0.0
    purpose: How do we continuously improve or retire the product?
    owner_role: adlc_coe
    status: active
  trigger:
    on: [T8.event.drift, T8.event.cost_overrun, T8.event.kpi_shortfall, T8.event.upstream_change, change.requested, lifecycle.review_due, T8.terminate, T7.terminate]
    mode: event
    lifecycle_review: {every: 12m}
  prerequisites:
    - {id: PRE-T9-01, evidence_ref: trigger.evidence, condition: exists, on_missing: block}
    - {id: PRE-T9-02, evidence_ref: T3.build_manifest.current, condition: exists, on_missing: block}
    - {id: PRE-T9-03, evidence_ref: T4.regression_pack.current, condition: exists, on_missing: warn}
  actors:
    agent: {id: t9-evolution-agent, model_tier: reasoning}
    subagents:
      - {id: impact-assessor, responsibility: "classify change, affected components, risk delta"}
      - {id: revalidation-planner, responsibility: "re-entry terminal and revalidation scope"}
      - {id: version-manager, responsibility: "version lifecycle: live, deprecated, sunset"}
      - {id: knowledge-curator, responsibility: "lessons learned into playbooks and knowledge base"}
      - {id: retirement-executor, responsibility: "decommission steps per retirement procedure"}
    reviewer: common-terminal-reviewer
    human_roles:
      - {role: product_owner, raci: A, scope: evolve}
      - {role: business_owner, raci: A, scope: retire}
      - {role: solution_architect, raci: C}
      - {role: service_owner, raci: R}
      - {role: data_owner, raci: R, scope: data_disposition}
  authorities:
    allow: [read:ledger.all, read:telemetry, write:T9.artifacts, raise:reentry_event, write:knowledge_base.lessons]
    deny: [write:repo, deploy:any, revoke:identity_without_approval]
    retirement: {allow: [disable:traffic, revoke:agent_identity, revoke:tool_scopes, archive:data, update:agent_registry], requires: business_owner_approval}
    data_access: {max_class: confidential_masked}
    tool_scopes: [mcp:agent_registry:write, mcp:iam:revoke, mcp:cmdb:write, mcp:confluence:write, mcp:servicenow:change_create]
    sign_off: {evolve: {roles: [product_owner], min_approvers: 1}, retire: {roles: [business_owner, service_owner, data_owner], min_approvers: 3}}
    status_rights: {reviewer: [recommend], human: [pass, rework, exception, terminate], orchestrator: [escalate]}
  playbooks:
    procedures:
      - {id: PB-T9-01, ref: playbooks/t9-change-impact.md, version: 1.0.0}
      - {id: PB-T9-02, ref: playbooks/version-lifecycle.md, version: 1.0.0}
      - {id: PB-T9-03, ref: playbooks/retirement.md, version: 1.0.0}
    grounding:
      - {mcp: confluence, scope: "/adlc/lessons-learned"}
      - {mcp: agent_registry, scope: "dependent agents and consumers"}
  change_classes:
    minor: {examples: [prompt wording, retrieval tuning, threshold-neutral config], reentry: T3, path: [T3, T4.regression_only, T6, T7]}
    moderate: {examples: [model version upgrade, new tool, memory change], reentry: T2, path: [T2.delta, T3, T4, T5.delta, T6, T7]}
    major: {examples: [autonomy level raised, new scope, new data class], reentry: T1, path: full}
    strategic: {examples: [business case no longer holds], reentry: T0, or: retire}
    emergency: {examples: [sev1 fix, safety patch], reentry: T3, path: [T3, T4.smoke, T7], retrospective: [T4, T5], within: 5d}
  retirement_procedure: [approve_and_communicate, disable_new_traffic, drain_or_handoff_in_flight, revoke_identity_scopes_secrets, dispose_memory_logs_data_per_retention, update_registry_and_cmdb, closure_report]
  controls:
    automated:
      - {id: CTL-T9-01, rule: "change_class assigned and reentry >= class minimum", severity: blocking}
      - {id: CTL-T9-02, rule: "autonomy or data class change => class >= major", severity: blocking}
      - {id: CTL-T9-03, rule: "model or tool change => class >= moderate", severity: blocking}
      - {id: CTL-T9-04, rule: "retire: all credentials revoked", severity: blocking}
      - {id: CTL-T9-05, rule: "retire: data disposition evidenced per T2 retention", severity: blocking}
      - {id: CTL-T9-06, rule: "retire: no dependent agent left unowned", severity: blocking}
    checklist:
      ref: checklists/t9.yaml
      items: [CHK-T9-01 classification rationale stated, CHK-T9-02 revalidation scope covers affected requirements, CHK-T9-03 lessons learned recorded, CHK-T9-04 users and dependants notified]
  evidence:
    artifacts:
      - {id: change_impact_assessment, format: table, columns: [trigger, change_class, affected_components, risk_delta, reentry_terminal], required: true}
      - {id: revalidation_plan, format: table, columns: [terminal, scope, owner, due], required: true}
      - {id: version_lifecycle_record, format: table, columns: [version, status, live_from, deprecated_on, sunset_on], required: true}
      - {id: lessons_learned, format: table, columns: [lesson, source_terminal, playbook_update], required: true}
      - {id: retirement_record, format: table, columns: [step, completed_on, evidence_link], required: on_retire}
      - {id: closure_report, format: signed_record, columns: [role, decision, date], required: on_retire}
    ledger: {key: "${usecase_id}/T9/${run_version}", immutable: true, retention: per_tier}
  outcome_model:
    pass: {route: "${change_impact_assessment.reentry_terminal}", or: lifecycle.closed}
    rework: {route: T9, requires: [owner_comment]}
    exception: {when: emergency, requires: [retrospective_plan]}
    escalate: {when: "classification disputed or rework_count > 3", route: adlc_coe}
    terminate: {set_by: business_owner, meaning: "retirement complete, lifecycle closed"}
  timeline:
    expected_duration: {assessment: 2d, retirement: {low: 5d, medium: 10d, high: 20d}}
    reminder_after: 2d
    escalate_after: 7d
    max_rework_cycles: 3
```

## 14. Cross-terminal evidence and routing map

The lifecycle holds together because each terminal's `emits` become a later terminal's `prerequisites` and `controls`. Three values carry most of the weight: the T0 risk tier, the T1 thresholds and the T3 package hash.

| Terminal | Key evidence consumed | Key evidence emitted | Pass → | Rework → (root cause) | Agent never may |
| --- | --- | --- | --- | --- | --- |
| T0 Intake | Free-text use case | risk\_tier, value\_hypothesis, RACI | T1 | T0 | Write outside T0 |
| T1 Requirements | T0 risk tier, value | eval/RAI thresholds, KPIs, autonomy levels | T2 | T1 / T0 | Edit T0 evidence |
| T2 Architecture | T1 NFRs, autonomy | design decisions, tool contracts, token budget | T3 | T2 / T1 | Provision infrastructure |
| T3 Build | T2 contracts | package sha256, build manifest | T4 | T3 / T2 | Merge to main, deploy |
| T4 Evaluation | T3 hash, T1 thresholds | eval baseline, regression pack | T5 | T3 / T2 / T1 | Change candidate or thresholds |
| T5 Assurance | T4 RAI evidence, T2 security | attestation, residual risk register | T6 | T3 / T2 | Accept residual risk |
| T6 Readiness | T0–T5 ledger | release authorisation, rollout plan | T7 | Owning terminal | Deploy, approve change |
| T7 Deployment | T6 authorisation, hash | registry entry, prod version | T8 | T3 / T6 / T7 (after auto-rollback) | Deploy an unauthorised hash |
| T8 Operate | T4 baseline, T1 KPIs, T6 alerts | lifecycle events | Continue | T8 | Change code or config |
| T9 Evolve/Retire | T8 events, manifest | change class, re-entry terminal | Re-entry T0–T7 or close | T9 | Revoke identity without approval |

**Event catalogue** (the only events the orchestrator accepts): `usecase.submitted`, `Tn.pass`, `Tn.exception`, `Tn.rework.<root_cause>`, `Tn.escalate`, `Tn.terminate`, `T7.rollback`, `T8.event.<type>`, `T9.reentry.Tn`, `change.requested`, `lifecycle.review_due`.

## 15. Open decisions

Numeric values in the YAML (coverage 80%, judge agreement 0.85, injection-success limits, case counts, SLAs, hypercare lengths) are proposed defaults and need owner confirmation before the specs move from draft to active.

- [ ] Confirm the proposed numeric defaults per terminal with each owning role
- [ ] Evidence ledger retention per risk tier (proposed 7 years high, 3 years otherwise)
- [ ] Ownership of shared checklists and playbooks: central ADLC CoE or terminal owners
- [ ] Maximum autonomy level allowed per risk tier (used by CTL-T1-05)
- [ ] Regulations in scope for the T5 regulatory map
- [ ] Whether T7 exceptions stay disallowed, and its rework limit of 2
- [ ] T8 review cadence and the N periods for a KPI shortfall event
- [ ] Model tiers (reasoning, coding, standard) mapped to approved models
- [ ] Spec versioning rule: do in-flight use cases stay on the YAML version they started with

## Annex A – Terminal definition explained (T3 example)

A terminal YAML is executed by three components: the **orchestrator** (when the terminal opens, who is involved, where the outcome routes), the **policy engine** (permissions and deterministic checks) and the **terminal agent** (what to build, how, and the definition of done).

### A.1 Block consumers

| Block | Read by | When | Effect |
| --- | --- | --- | --- |
| trigger | Orchestrator | Continuously | Opens a run |
| prerequisites | Orchestrator | On open | Admits or blocks the run |
| actors | Orchestrator | On open | Starts agents, notifies humans |
| authorities | Policy engine / identity service | On open and every tool call | Grants and constrains permissions |
| playbooks | Terminal agent | During build | Procedure and grounding |
| controls | Policy engine, then reviewer agent | After build | Deterministic checks, then judgement checks |
| evidence | Orchestrator + ledger | Before close | Definition of done |
| outcome\_model | Orchestrator | After sign-off | Routing |
| timeline | Orchestrator timers | Throughout | Reminders and escalation |

### A.2 Attribute semantics (T3)

| Block | Attribute / value | Meaning |
| --- | --- | --- |
| trigger | `T2.pass`, `T2.exception` | Normal entry after approved design |
| trigger | `T4.rework.implementation` | Eval failure caused by code returns to T3, not T2 |
| trigger | `T5.rework.control_missing` | Security control missing in build returns to T3 |
| trigger | `T7.rollback` | Production rollback returns to T3 |
| trigger | `T9.reentry.T3` | Minor change enters directly at T3 |
| prerequisites | PRE-T3-01 | T2 status is pass or exception |
| prerequisites | PRE-T3-02 | Tool/API contracts exist |
| prerequisites | PRE-T3-03 | Dev environment provisioned |
| prerequisites | PRE-T3-04 | Template version pinned, guaranteeing reproducible builds |
| prerequisites | `on_missing: block` | Run held as blocked and owner notified; `warn` proceeds with a flag |
| actors | `agent: t3-builder-agent` | Registered agent definition |
| actors | `model_tier: coding` | Resolved to the approved model via the model catalogue |
| actors | `subagents[].responsibility` | Scope of each subagent |
| actors | `human_roles` RACI | A = signer, R = action items, C/I = read access and updates |
| authorities | `allow: write:repo.feature_branch, open:pull_request` | Agent writes and proposes code |
| authorities | `deny: merge:main, deploy:*, write:T1.thresholds` | Agent cannot merge, deploy, or alter its test bar; deny overrides allow |
| authorities | `data_access: synthetic_or_masked` | No production data during build |
| authorities | `tool_scopes` | Run-scoped MCP scopes, revoked at close |
| authorities | `sign_off.plus` | Solution architect added only if `design_conformance` shows a deviation |
| authorities | `status_rights` | Agent sets no status; reviewer recommends; humans decide; orchestrator escalates |
| playbooks | `procedures` | Loaded into agent context; versions recorded in the ledger |
| playbooks | `grounding` | Read-only knowledge sources (component catalogue, standards, MCP registry) |
| controls | `automated`, `severity: blocking` | Policy engine checks; run cannot reach review until passed |
| controls | `automated`, `severity: advisory` | Shown to reviewer; does not block |
| controls | `checklist` | Judgement items evaluated by the common reviewer agent |
| evidence | `artifacts[].required: true` | Run cannot close without the artifact in the declared column schema |
| evidence | `candidate_package.sha256` | Binding key used by T4, T5, T6 and T7 |
| evidence | `ledger.key`, `immutable: true` | One permanent record per run; reruns do not overwrite |
| outcome\_model | `pass → T4`, `emits` | Publishes package hash and manifest |
| outcome\_model | `rework.route_by_root_cause` | `implementation → T3`, `design → T2`; owner comment passed to next run |
| outcome\_model | `exception.recheck_at: T6` | Waiver revalidated at Release Readiness |
| outcome\_model | `escalate` | Automatic after 3 rework cycles or `escalate_after` |
| outcome\_model | `terminate` | Business owner only, with reason |
| timeline | `expected_duration` | Selected by T0 risk tier: low 5d, medium 10d, high 15d |
| timeline | `reminder_after`, `escalate_after` | 5d reminder, 20d escalation |
| timeline | `max_rework_cycles` | 3 |

### A.3 Example run (medium risk tier)

| Step | Actor | Action | YAML block |
| --- | --- | --- | --- |
| 1 | Orchestrator | Receives `T2.pass`; opens T3 run 1 | trigger |
| 2 | Orchestrator | Validates PRE-T3-01 to PRE-T3-04 against the ledger | prerequisites |
| 3 | Identity service | Issues run-scoped identity and MCP scopes | authorities |
| 4 | Orchestrator | Starts builder agent and subagents; assigns tasks to engineering\_lead and sre | actors |
| 5 | Builder agent | Builds per PB-T3-01 to PB-T3-03; opens PRs; humans merge; CI runs | playbooks, authorities |
| 6 | Policy engine | CTL-T3-02 fails (coverage 72%); run returned to agent | controls.automated |
| 7 | Builder agent | Raises coverage to 84%; all blocking controls pass | controls.automated |
| 8 | Reviewer agent | Evaluates CHK-T3-01 to CHK-T3-06; one approved deviation found; recommends pass | controls.checklist |
| 9 | Orchestrator | Adds solution\_architect as approver due to deviation; both sign | authorities.sign\_off |
| 10 | Orchestrator | Writes ledger record `UC-0042/T3/run-1`; emits package hash | evidence |
| 11 | Orchestrator | Publishes `T3.pass`; T4 opens and requires the emitted hash | outcome\_model |
| — | Orchestrator timers | Target 10d; reminder 5d; escalation 20d | timeline |

**Note:** automated-control retries (steps 6–7) do not count toward `max_rework_cycles`; a separate `max_auto_retries` limit is to be confirmed.

## Annex B – Terminal YAML data dictionary

Every terminal YAML must conform to this dictionary (schema version 1.0.0). The spec loader rejects any spec that has unknown fields, wrong types or missing required fields.

### B.1 Data types

| Type | Format | Example |
| --- | --- | --- |
| string | UTF-8 text | `Build & Integration` |
| id | Unique code within the spec: upper-case for checks (`PRE-`, `CTL-`, `CHK-`, `PB-`, `MON-`), kebab-case for agents | `CTL-T3-02`, `t3-builder-agent` |
| semver | MAJOR.MINOR.PATCH | `1.0.0` |
| enum | One value from a list in B.2 | `blocking` |
| int / bool | Integer / true or false | `3`, `true` |
| duration | Integer + unit: `h` hours, `d` days, `w` weeks, `m` months | `72h`, `10d`, `12m` |
| evidence\_ref | `Tn.<artifact>[.<field>]`, resolved in the ledger for the same use case | `T2.tool_api_contracts` |
| event | `<source>.<outcome>[.<qualifier>]` from the event catalogue | `T4.rework.implementation` |
| permission | `<verb>:<resource>[.<qualifier>]` | `write:repo.feature_branch` |
| scope | `mcp:<server>:<scope>` | `mcp:git:branch_write` |
| path | Repository-relative file path | `playbooks/t3-build.md` |
| template | String with `${…}` variables resolved at run time | `${usecase_id}/T3/${run_version}` |
| expr | Boolean expression evaluated by the policy engine (B.3) | `unit_coverage >= 80%` |
| tiered\<T> | A single T, or a map `{low, medium, high}` of T | `{low: 5d, medium: 10d, high: 15d}` |

### B.2 Enumerations

| Enumeration | Values | Used in |
| --- | --- | --- |
| spec\_status | draft, active, deprecated, retired | metadata.status |
| trigger\_mode | event, scheduled, continuous | trigger.mode |
| on\_missing | block, warn | prerequisites\[\].on\_missing |
| model\_tier | reasoning, coding, standard | actors.agent.model\_tier |
| raci | R, A, C, I | actors.human\_roles\[\].raci |
| role | Role catalogue (section 3) | human\_roles, sign\_off, set\_by, notify |
| data\_class | public, internal, synthetic\_or\_masked, confidential\_masked, confidential, restricted; or `per_T2_prod_design` | authorities.data\_access.max\_class |
| severity | blocking, advisory | controls.automated\[\].severity |
| risk\_tier | low, medium, high | tiering, timeline, sign\_off, applies |
| artifact\_format | table, diagram+table, document, reference, signed\_record | evidence.artifacts\[\].format |
| outcome\_status | pass, rework, exception, escalate, terminate | outcome\_model, status\_rights |
| actor\_class | agent, reviewer, human, orchestrator | status\_rights keys |
| status\_right | outcome\_status values, plus recommend, raise\_event, rework\_on\_auto\_rollback | status\_rights values |
| root\_cause | qualification, requirement, design, architecture, implementation, control\_missing, missing\_evidence, ops\_gap, defect, readiness\_gap, environment | rework.route\_by\_root\_cause |
| change\_class | minor, moderate, major, strategic, emergency | change\_classes (T9) |

### B.3 Expression syntax

| Element | Syntax | Example |
| --- | --- | --- |
| Comparison | `==  !=  >  >=  <  <=` | `sast.critical == 0` |
| Membership | `in [a, b]` | `T2.status in [pass, exception]` |
| Logic | `and  or  not` | `rework_count > 3 or age > escalate_after` |
| Existence | `exists`, `signed`, `frozen`, `provisioned` | `T5.assurance_attestation signed` |
| Ledger reference | `${Tn.<artifact>.<field>}` | `${T1.eval_thresholds.task_success}` |
| Tier parameter | `tier.<param>` | `tier.max_injection_success` |
| Run variables | `rework_count`, `age`, `now`, `usecase_id`, `run_version`, `risk_tier` | `age > 7d` |

### B.4 Field dictionary

Req: Y = required · N = optional · C = conditional (the condition is in the description).

| Field path | Type | Req | Default | Description |
| --- | --- | --- | --- | --- |
| **metadata** |  |  |  |  |
| metadata.id | id (T0–T9) | Y | — | Terminal identifier; registry key; prefix of events and ledger keys |
| metadata.name | string | Y | — | Display name |
| metadata.version | semver | Y | — | Spec version; every change creates a new version |
| metadata.purpose | string | Y | — | Question the terminal answers; passed to the agent as its goal |
| metadata.owner\_role | role | Y | adlc\_coe | Role that approves changes to this spec |
| metadata.status | spec\_status | Y | draft | Only `active` specs accept new use cases |
| metadata.schema\_version | semver | N | 1.0.0 | Dictionary version the spec conforms to |
| **trigger** |  |  |  |  |
| trigger.on | list\<event> | Y | — | Events that open a run; at least one |
| trigger.mode | trigger\_mode | Y | event | Run type |
| trigger.schedule | cron | C | — | Required when mode = scheduled |
| trigger.window | template | N | — | Time window the run may execute in (T7 change window) |
| trigger.review\_schedule | tiered\<string> | C | — | Periodic review cadence; required when mode = continuous (T8) |
| trigger.lifecycle\_review.every | duration | N | — | Scheduled re-assessment interval (T9) |
| **prerequisites\[\]** |  |  |  |  |
| prerequisites\[\].id | id | Y | — | `PRE-Tn-nn`, unique in the spec |
| prerequisites\[\].evidence\_ref | evidence\_ref | Y | — | Ledger evidence to check |
| prerequisites\[\].condition | expr | Y | exists | Rule the evidence must satisfy |
| prerequisites\[\].on\_missing | on\_missing | Y | block | `block` holds the run; `warn` proceeds with a flag |
| **actors** |  |  |  |  |
| actors.agent.id | id | Y | — | Agent in the lifecycle agent registry |
| actors.agent.model\_tier | model\_tier | Y | standard | Resolved to an approved model via the model catalogue |
| actors.subagents\[\].id | id | N | — | Subagent in the lifecycle agent registry |
| actors.subagents\[\].responsibility | string | C | — | Task boundary; required for each subagent |
| actors.reviewer | id | Y | common-terminal-reviewer | Reviewer agent |
| actors.human\_roles\[\].role | role | Y | — | Resolved to named people through the T0 RACI |
| actors.human\_roles\[\].raci | raci | Y | — | Exactly one A per scope |
| actors.human\_roles\[\].scope | string | N | whole terminal | Narrows the role's accountability (e.g. residual\_risk\_acceptance) |
| **authorities** |  |  |  |  |
| authorities.allow | list\<permission> | Y | — | Actions granted to the run identity |
| authorities.deny | list\<permission> | Y | — | Prohibited actions; overrides allow |
| authorities.emergency.allow / when / notify | list\<permission> / expr / list\<role> | N | — | Actions allowed only while `when` is true, with roles alerted (T8) |
| authorities.retirement.allow / requires | list\<permission> / role | N | — | Decommission actions and their approval (T9) |
| authorities.data\_access.max\_class | data\_class | Y | internal | Highest data classification the agents may access |
| authorities.tool\_scopes | list\<scope> | Y | \[\] | Run-scoped MCP permissions; must exist in the MCP registry |
| authorities.sign\_off.roles | list\<role> | Y | — | Approver roles |
| authorities.sign\_off.min\_approvers | int ≥ 1 | Y | 1 | Approvals required to close |
| authorities.sign\_off.plus | string | N | — | Conditional extra approver (e.g. architect on design deviation) |
| authorities.sign\_off.\<tier> | object | N | — | Sign-off overriding the default for a risk tier (T5) |
| authorities.sign\_off.\<mode> | object | N | — | Sign-off per mode, e.g. evolve / retire (T9) |
| authorities.sign\_off.board / external | string | N | — | Board or external body (RAI board, CAB) |
| authorities.sign\_off.stage\_approval | map\<stage, role> | N | — | Approval for a stage inside the run (T7 full rollout) |
| authorities.status\_rights | map\<actor\_class, list\<status\_right>> | Y | template default | Which actor may set which outcome |
| **playbooks** |  |  |  |  |
| playbooks.procedures\[\].id | id | Y | — | `PB-Tn-nn` |
| playbooks.procedures\[\].ref | path | Y | — | Playbook file |
| playbooks.procedures\[\].version | semver | Y | — | Pinned playbook version; recorded in the ledger |
| playbooks.procedures\[\].applies\_when | expr | N | always | Condition for loading the playbook |
| playbooks.grounding\[\].mcp | string | N | — | MCP server from the MCP registry |
| playbooks.grounding\[\].scope | string | C | — | Read scope; required when mcp is set |
| **controls** |  |  |  |  |
| controls.automated\[\].id | id | Y | — | `CTL-Tn-nn` |
| controls.automated\[\].rule | expr | Y | — | Deterministic check |
| controls.automated\[\].severity | severity | Y | blocking | `blocking` stops the run before review |
| controls.automated\[\].applies | list\<risk\_tier> | N | all tiers | Tiers the control applies to |
| controls.auto\_rollback\_on | list\<id> | N | — | Controls whose failure triggers rollback (T7) |
| controls.checklist.ref | path | Y | — | Checklist file |
| controls.checklist.items | list\<id + text> | Y | — | Judgement items scored by the reviewer agent |
| controls.tiering.\<tier> | map | N | — | Parameter overrides per risk tier; read as `tier.<param>` |
| **monitors\[\]** (T8) |  |  |  |  |
| monitors\[\].id | id | C | — | `MON-nn`; required when mode = continuous |
| monitors\[\].signal | string | Y | — | Telemetry signal name |
| monitors\[\].threshold | expr | Y | — | Breach condition |
| monitors\[\].raises | event | Y | — | Event published on breach |
| **change\_classes** (T9) |  |  |  |  |
| change\_classes.\<class>.examples | list\<string> | Y | — | Changes that fall in the class |
| change\_classes.\<class>.reentry | terminal id | Y | — | Re-entry terminal |
| change\_classes.\<class>.path | list\<terminal\[.mode\]> or `full` | Y | — | Terminals executed for the change |
| change\_classes.\<class>.retrospective / within | list\<terminal> / duration | N | — | Post-hoc validation for emergency changes |
| retirement\_procedure | list\<string> | C | — | Ordered decommission steps; required in T9 |
| **evidence** |  |  |  |  |
| evidence.artifacts\[\].id | id | Y | — | Artifact name; referenced as `Tn.<id>` |
| evidence.artifacts\[\].format | artifact\_format | Y | table | Structure of the artifact |
| evidence.artifacts\[\].columns | list\<string> | Y | — | Required columns, in order |
| evidence.artifacts\[\].required | bool or condition | Y | true | Close is blocked while a required artifact is missing |
| evidence.ledger.key | template | Y | `${usecase_id}/Tn/${run_version}` | Ledger address of the run record |
| evidence.ledger.immutable | bool | Y | true | Write-once record |
| evidence.ledger.bound\_to | evidence\_ref | N | — | Binds evidence to the candidate package hash |
| evidence.ledger.retention | duration or `per_tier` | Y | per\_tier | Retention period |
| **outcome\_model** |  |  |  |  |
| outcome\_model.\<status>.route | terminal id, event or template | C | — | Destination; required for pass |
| outcome\_model.rework.route\_by\_root\_cause | map\<root\_cause, terminal> | C | — | Root-cause routing; required unless rework.route is set |
| outcome\_model.\<status>.emits | list\<string> | N | — | Values published to the ledger for later terminals |
| outcome\_model.\<status>.requires | list\<string> | N | — | Mandatory fields when setting the status |
| outcome\_model.\<status>.when | expr | C | — | Automatic condition; required for escalate |
| outcome\_model.\<status>.set\_by | role or list\<role> | N | per status\_rights | Overrides who may set the status |
| outcome\_model.\<status>.recheck\_at | list\<terminal> | N | — | Terminals that revalidate a waiver |
| outcome\_model.\<status>.not\_allowed | bool | N | false | Disables the status (T7 exception) |
| outcome\_model.\<status>.notify / then | list\<role> / event | N | — | Extra notifications; follow-on event |
| outcome\_model.event\_routes.\<event> | map | N | — | Routing for operational events: route, immediate, then, notify (T8) |
| **timeline** |  |  |  |  |
| timeline.expected\_duration | tiered\<duration> or `continuous` | Y | — | Target duration |
| timeline.reminder\_after | duration | Y | — | Reminder timer |
| timeline.escalate\_after | duration or `window_end` | Y | — | Escalation timer |
| timeline.max\_rework\_cycles | int | Y | 3 | Rework limit before automatic escalate |
| timeline.review\_due | string | C | — | Review deadline rule; required when mode = continuous |

### B.5 Spec validation rules (applied by the spec loader)

| Rule | Check |
| --- | --- |
| V-01 | All IDs unique within the spec; terminal ID unique in the registry |
| V-02 | Every `evidence_ref` resolves to an artifact or emitted value of an earlier terminal |
| V-03 | Every event in `trigger.on` is emitted by at least one terminal |
| V-04 | Every non-terminating outcome has a route |
| V-05 | Every role exists in the role catalogue; every `sign_off` role holds A or R in `human_roles` |
| V-06 | Every tool scope and grounding server exists in the MCP registry |
| V-07 | No permission appears in both allow and deny |
| V-08 | Every tiered value defines low, medium and high |
| V-09 | `status_rights.agent` never contains pass, exception or terminate |
| V-10 | Every playbook and checklist `ref` exists at the stated version |

## Annex C – Terminal data model

The model has two layers: the **spec model** (design time: what a terminal YAML contains, stored in the spec registry) and the **runtime model** (run time: what each terminal run records). Entity names are logical; for the MVP both layers map to Postgres tables.

### C.1 Spec model

&#91;embedded content: spec model · TERMINAL\_SPEC and its child entities by YAML block\]

Each container is one YAML block; entity names are in capitals, followed by cardinality and key fields.

| Entity | Parent | Cardinality | Key | YAML source |
| --- | --- | --- | --- | --- |
| TERMINAL\_SPEC | — | 1 per terminal version | terminal\_id, version | metadata |
| TRIGGER\_EVENT | TERMINAL\_SPEC | 1..\* | event\_type | trigger.on |
| PREREQUISITE | TERMINAL\_SPEC | 1..\* | prereq\_id | prerequisites\[\] |
| ACTOR | TERMINAL\_SPEC | 1..\* | actor\_id | actors.agent, subagents\[\], reviewer |
| ROLE\_ASSIGNMENT | TERMINAL\_SPEC | 1..\* | role, scope | actors.human\_roles\[\] |
| PERMISSION | TERMINAL\_SPEC | 1..\* | permission, effect | authorities.allow, deny, emergency, retirement |
| TOOL\_SCOPE | TERMINAL\_SPEC | 0..\* | scope | authorities.tool\_scopes |
| SIGN\_OFF\_RULE | TERMINAL\_SPEC | 1..\* | tier or mode | authorities.sign\_off |
| STATUS\_RIGHT | TERMINAL\_SPEC | 1..\* | actor\_class | authorities.status\_rights |
| PLAYBOOK | TERMINAL\_SPEC | 1..\* | playbook\_id | playbooks.procedures\[\] |
| GROUNDING\_SOURCE | TERMINAL\_SPEC | 0..\* | mcp, scope | playbooks.grounding\[\] |
| CONTROL | TERMINAL\_SPEC | 1..\* | control\_id | controls.automated\[\] |
| CHECKLIST\_ITEM | TERMINAL\_SPEC | 1..\* | item\_id | controls.checklist.items |
| TIER\_PROFILE | TERMINAL\_SPEC | 0..3 | risk\_tier | controls.tiering |
| ARTIFACT\_DEF | TERMINAL\_SPEC | 1..\* | artifact\_id | evidence.artifacts\[\] |
| ARTIFACT\_COLUMN | ARTIFACT\_DEF | 1..\* | artifact\_id, column\_name | evidence.artifacts\[\].columns |
| LEDGER\_POLICY | TERMINAL\_SPEC | 1 | terminal\_id, version | evidence.ledger |
| OUTCOME\_ROUTE | TERMINAL\_SPEC | 5..\* | status, root\_cause | outcome\_model |
| EVENT\_ROUTE | TERMINAL\_SPEC | 0..\* | event\_type | outcome\_model.event\_routes (T8) |
| TIMELINE\_POLICY | TERMINAL\_SPEC | 1..3 | risk\_tier | timeline |
| MONITOR | TERMINAL\_SPEC | 0..\* | monitor\_id | monitors (T8) |
| CHANGE\_CLASS | TERMINAL\_SPEC | 0..\* | change\_class | change\_classes (T9) |
| RETIREMENT\_STEP | TERMINAL\_SPEC | 0..\* | sequence | retirement\_procedure (T9) |

Shared catalogues (ROLE, RISK\_TIER, EVENT\_TYPE, MODEL\_TIER, DATA\_CLASS, MCP\_SERVER) are maintained in `adlc/shared/*.yaml` and referenced by key.

### C.2 Runtime model

&#91;embedded content: runtime model · TERMINAL\_RUN and the records it produces\]

LEDGER\_RECORD and OUTBOX\_EVENT are written in one database transaction, so a terminal outcome and the event that opens the next run always exist together.

| Entity | Key | Main attributes | Written by | When |
| --- | --- | --- | --- | --- |
| SPEC\_REGISTRY | terminal\_id, version | status, spec\_yaml, spec\_json, content\_hash, trigger\_events, emitted\_events | Spec CI | Spec approval |
| USECASE\_SPEC\_PIN | usecase\_id, terminal\_id | version, pinned\_at, pinned\_reason | Orchestrator | T0 start; T9 upgrade |
| USECASE | usecase\_id | name, business\_owner, risk\_tier, status, created\_at | Orchestrator | Submission; risk tier set at T0 pass |
| TERMINAL\_RUN | run\_id (`usecase_id/terminal_id/run_version`) | spec\_version, trigger\_event\_id, status, recommended\_status, rework\_count, opened\_at, due\_at, closed\_at | Orchestrator | Run open; each step |
| PREREQUISITE\_RESULT | run\_id, prereq\_id | evidence\_ref, result, checked\_at | Orchestrator | Open |
| CONTROL\_RESULT | run\_id, control\_id, attempt | measured\_value, result, severity, evaluated\_at | Policy engine | Verify, every attempt |
| CHECKLIST\_RESULT | run\_id, item\_id | score, finding, evidence\_link | Reviewer agent | Review |
| RUN\_ARTIFACT | run\_id, artifact\_id | uri, content\_hash, schema\_valid, produced\_by | Terminal agent | Execute |
| SIGN\_OFF | run\_id, role, person | decision, comment, root\_cause, signed\_at | Terminal owners | Decide |
| WAIVER | waiver\_id | run\_id, owner, expiry, compensating\_control, recheck\_at, status | Owner / risk owner | Exception outcome |
| LEDGER\_RECORD | ledger\_key | run\_id, final\_status, spec\_hash, bound\_to, record\_hash, written\_at | Orchestrator | Close |
| OUTBOX\_EVENT | event\_id | event\_type, usecase\_id, payload, causation\_run\_id, attempts, processed\_at | Orchestrator | Close; T7 and T8 events |
