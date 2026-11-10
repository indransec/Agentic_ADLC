# Agentic ADLC Platform – Solution Architecture (MVP, Extensible by Design)

Nov 6, 2026 · @Indrajit

## 1. Document context

This document defines the solution architecture of the Agentic ADLC Platform: the system that drives an agentic use case through terminals T0–T9 using AI agents, with humans supervising every decision. It is designed for the mid-December 2026 MVP, but every component is chosen so later iterations extend it rather than replace it.

**Audience:** ADLC CoE, platform engineering, terminal owners (security, privacy, RAI, QA, release, operations), enterprise architecture.

**In scope (MVP)**

- Lifecycle platform: spec layer, orchestration, lifecycle agents, policy enforcement, evidence ledger, human approval and lifecycle dashboard.
- One pilot use case (Travel Claims Assistant, synthetic data) with one agent, two at most, taken from T0 to T9.
- Simulated deployment (T7) and simulated operations (T8) for the pilot.

**Recorded as target state, not built in MVP:** multiple concurrent use cases and teams, real enterprise integrations (ITSM, CMDB, production CI/CD), subagent-level permissions, portfolio analytics, spec signing, automated spec simulation.

**Out of scope:** the internal design of the pilot use case itself (owned by its own T2 design contract), and enterprise model hosting.

**Key constraints and assumptions**

| # | Constraint / assumption |
| --- | --- |
| C-1 | MVP demonstrable by mid-December 2026, with a full T0→T9 run in a single demo session |
| C-2 | Synthetic data only; no production or customer data in MVP |
| C-3 | Terminal specs never hold use-case-specific values (section 5) |
| C-4 | Specs, playbooks and checklists live in the platform repo for MVP |
| C-5 | Hosting target not yet decided; MVP runs on a single containerised environment (section 15) |
| C-6 | Enterprise integrations are mocked where not available, behind the same interfaces as the real ones |

**References:** Terminal-Based Agentic ADLC – Terminal Design Specification (terminal specs T0–T9, data dictionary Annex B, data model Annex C); ADLC lifecycle sample run (draw.io); terminal data model (draw.io).

## 2. Architecture drivers and principles

The MVP must prove one thing: AI agents can carry an agentic use case through the full lifecycle while humans keep every decision. The architecture is judged by whether the demo shows that clearly, and whether the same design scales to many use cases without rework.

**Business drivers**

- Standardise how agents are qualified, built, assured, released, operated and retired across teams.
- Cut lifecycle effort by letting agents produce the artifacts, with humans reviewing rather than authoring.
- Make every lifecycle decision auditable: who decided, on what evidence, under which rules.

**Demo success criteria**

| # | The audience must see |
| --- | --- |
| D-1 | Agent builds → reviewer agent recommends → human decides, at every terminal |
| D-2 | A human rejection with comment, then agent rework using that comment |
| D-3 | Root-cause routing across terminals (e.g. a T4 defect returns to T3) |
| D-4 | Escalation to a human after 3 rework cycles |
| D-5 | An exception with a waiver, rechecked at T6 |
| D-6 | Package hash integrity: what T4 tested is what T7 deployed |
| D-7 | A T8 event → T9 classification → lifecycle re-entry or retirement |
| D-8 | A live dashboard of progression, reroutes, agent and human activity, time, reworks and escalations |
| D-9 | An agent asks for missing information, a human answers, and the same run resumes without counting as rework |

**Architecture principles**

| # | Principle | Consequence |
| --- | --- | --- |
| P-1 | **Spec-driven** | The lifecycle is defined in versioned YAML specs; changing the lifecycle is a spec change, not a code release |
| P-2 | **Superset, not values** | Terminal specs define what must be captured; values come from enterprise guardrails and the use-case profile; a use case may use a declared subset |
| P-3 | **Agents build, humans decide** | Agents produce and recommend; only humans pass, waive or terminate |
| P-4 | **Separation of duties** | The builder cannot evaluate, the evaluator cannot change the candidate or thresholds, the deployer cannot change code; enforced by permissions, not prompts |
| P-5 | **Evidence-first** | Every terminal writes an immutable, hashed ledger record; later terminals read evidence only from the ledger |
| P-6 | **Deterministic where possible** | Machine-checkable rules run in a policy engine; agents judge only what needs judgement |
| P-7 | **Deny by default** | Agents get run-scoped permissions and data ceilings; anything not granted is refused |
| P-8 | **Extensible by configuration** | New controls, metrics, approvers and terminals are added through specs and shared catalogues |
| P-9 | **Same interfaces, mocked or real** | MVP mocks sit behind the interfaces real integrations will use, so swapping them changes no platform code |
| P-10 | **Observable by design** | Every step emits an activity record and a trace, so the dashboard is a view over data the platform already holds |

## 3. Requirements summary

**Functional requirements**

| ID | Requirement | MVP | Post-MVP |
| --- | --- | --- | --- |
| FR-01 | Start a lifecycle when a business owner submits a use case in free text | Yes | — |
| FR-02 | Run T0–T9 as terminals defined by versioned YAML specs, pinned per use case | Yes | Spec bundles |
| FR-03 | Each terminal: prerequisites → agent build → automated controls → reviewer recommendation → human sign-off → route | Yes | — |
| FR-04 | Five outcomes (pass, rework, exception, escalate, terminate) with root-cause routing | Yes | — |
| FR-05 | Rework carries the human comment into the next agent run; escalate after 3 cycles; terminate by human only | Yes | Per-terminal limits |
| FR-06 | Exceptions with waiver owner, expiry and compensating control; rechecked at T6 and T8 | Yes | — |
| FR-07 | Use-case profile: applicable subset of artifacts and metrics, thresholds, KPIs, parameters, set at T0–T2 | Yes | Profile versioning via T9 |
| FR-08 | Immutable evidence ledger with content hashes; package hash bound from T3 to T7 | Yes | Signing, WORM storage |
| FR-09 | Simulated deployment (T7) with rollout stages and smoke validation | Yes (simulated) | Real CI/CD and environments |
| FR-10 | T8 monitors on synthetic traffic raising events; T9 change classification and re-entry or retirement | Yes (2–3 monitors) | Full monitor set |
| FR-11 | Human inbox for sign-offs, rework comments, escalation completion, waivers and clarifications | Yes | Teams / ServiceNow approvals |
| FR-12 | Lifecycle dashboard: journey, run detail, activity feed, KPIs | Yes (single use case) | Portfolio view |
| FR-13 | Spec authoring, validation and registration through Git and CI | Yes | Authoring UI, automated simulation |
| FR-14 | Agents may pause a run to ask the accountable role for missing information; the answer resumes the same run, is kept as evidence and does not count as rework | Yes | Clarification analytics |

**Non-functional requirements**

| ID | Quality | MVP requirement | Target state |
| --- | --- | --- | --- |
| NFR-01 | Auditability | Every decision, artifact, check and event traceable to a spec version and hash | Plus signed specs and evidence |
| NFR-02 | Reliability | Runs survive process restarts; no lost or duplicated lifecycle events | HA across zones |
| NFR-03 | Security | Run-scoped agent identity; deny-by-default permissions; secrets outside code | Enterprise IAM, workload identity federation |
| NFR-04 | Performance | Dashboard refresh ≤ 10 s; routing decision ≤ 2 s after an outcome | Streaming updates |
| NFR-05 | Scalability | One use case, sequential terminals | Hundreds of concurrent use cases |
| NFR-06 | Cost | Lifecycle agent token cost tracked per terminal | Budgets and alerts per use case |
| NFR-07 | Extensibility | New controls, metrics and approvers without platform code change | New terminals and integrations without code change |
| NFR-08 | Usability | A non-technical owner can review and approve a terminal in the inbox | Role-based views |

## 4. Architecture overview

The platform is one system with seven layers. People act only through the experience layer, agents act only through the orchestration and policy layers, and everything that happens is recorded in the data and evidence layer.

### 4.1 System context

&#91;embedded content: system context · 4 human actor groups, 6 external systems\]

People start lifecycles and make every decision; the platform reaches enterprise systems only through governed integrations, and builds and runs the pilot agent in its own environments.

### 4.2 Logical architecture

&#91;embedded content: logical architecture · 7 layers plus cross-cutting observability\]

| Layer | Components | Responsibility |
| --- | --- | --- |
| Experience | Intake form, approval inbox, journey view, KPI dashboard | One web app for every human action and for lifecycle visibility |
| Orchestration | Event router, workflow engine, SLA timers, outbox | Opens terminal runs from events, drives each run's steps, applies routing, runs timers |
| Agents | Lifecycle agents T0–T9, reviewer agent, context builder, model gateway | Produce artifacts and recommendations from a context pack; reach models through one gateway |
| Policy | Policy engine, approval service, token service | Enforce prerequisites, controls and permissions; collect sign-offs; issue run-scoped identities |
| Specs & config | Spec registry, catalogues, guardrails, playbooks | Versioned definition of the lifecycle and its enterprise limits |
| Data & evidence | Evidence ledger, run and activity data, use-case profile, object store | Immutable evidence, run state and the per-use-case values |
| Integration | MCP servers for knowledge, Git and CI, test harnesses, ITSM and deployment (mocked where needed) | Governed access to enterprise and pilot systems |
| Observability (cross-cutting) | Traces, run activity, KPI views, service health | Lifecycle visibility for people, platform health for engineers |

Editable sources: pages 1 and 2 of `adlc-solution-architecture.drawio`.

## 5. Spec and configuration layer

The lifecycle is defined entirely by configuration in three layers. Terminal specs say **what** must be captured and checked; enterprise guardrails say **what no use case may cross**; the use-case profile says **what this use case targets**. Terminal specs reference the other two layers and never hold use-case values.

### 5.1 Value layers

| Layer | Holds | Owned by | Lives in | Changes through |
| --- | --- | --- | --- | --- |
| Terminal specs | Artifacts and attributes (with applicability), generic controls, routing, roles, permissions, timelines | ADLC CoE + terminal owners | `specs/terminals/T0–T9.yaml` | Spec PR and release |
| Shared catalogues | Roles, risk tiers, event catalogue, data classes, model tiers, MCP servers, root causes, predicates, **metric catalogue** | ADLC CoE | `specs/shared/*.yaml` | Spec PR and release |
| Enterprise guardrails | Floors, ceilings and defaults per risk tier (e.g. max injection success, min coverage, mandatory RAI metric classes) | CoE + security, RAI, QA owners | `specs/shared/guardrails.yaml` | Spec PR, major-change approval |
| Use-case profile | Applicable subset with reasons, selected and custom metrics with thresholds, KPIs, parameter values, autonomy levels, token budget | Use-case owners, approved at T0–T2 | Evidence ledger | T0–T2 sign-off; later only through T9 |

### 5.2 Superset and applicability

- Every artifact, attribute, metric requirement and control in a terminal spec carries `applicability`: `mandatory`, `conditional` (with a predicate, e.g. `usecase.uses_memory`) or `optional`.
- At T0 and T1 the agents propose the applicable subset; each "not applicable" carries a reason; the reviewer checks reasons; mandatory items cannot be dropped.
- Controls iterate over the profile rather than naming metrics, e.g. *every applicable quality metric meets its use-case threshold*.

### 5.3 Metric catalogue

One shared definition per metric: name, class (quality, RAI, cost, latency, reliability, business KPI), unit, direction, measurement method. T1 selects metrics from the catalogue and proposes targets; use cases may add custom metrics to their own profile without changing the catalogue.

### 5.4 Parameter resolution

At run open, each referenced value resolves in this order: **use-case value (if within guardrails) → guardrail tier default**. Safety and assurance limits are `tighten_only`: a use case may make them stricter, never looser; loosening requires an exception. The resolved set is frozen on the terminal run for audit.

### 5.5 Spec lifecycle (MVP)

| Step | Mechanism |
| --- | --- |
| Author | YAML on a feature branch; IDE schema validation; playbooks and checklists in the same PR |
| Validate | `adlc-spec validate`: parse, JSON Schema, single-spec rules, cross-spec graph and references, version-bump rules |
| Approve | Pull request with CODEOWNERS per terminal; governance board for major changes |
| Register | On merge, release job writes `spec_registry` + projection tables in one transaction; previous version deprecated |
| Consume | Use cases pin active versions at T0; each run verifies the content hash |
| Retire | Allowed only when no use case is pinned |

Conditions in specs are expressions in CEL or named predicates from `predicates.yaml`; free-text conditions in the current specs are converted before MVP build.

## 6. Lifecycle orchestration

Every terminal runs the same flow; only its spec differs. Events open runs, a durable workflow drives each run through its steps, and the outcome is written to the ledger together with the event that opens the next run.

### 6.1 Terminal run flow

&#91;embedded content: terminal run flow · identical for T0–T9\]

Unmet prerequisites hold the run in a blocked state and notify the owner. Escalate is set only by the orchestrator; terminate only by a human. An agent (or the reviewer) missing information pauses the run in awaiting\_clarification; the human's answer resumes the same run and does not count as rework.

### 6.2 Run states

| State | Entered when | Leaves when |
| --- | --- | --- |
| opened | Router starts a run for a matching event | Prerequisites evaluated |
| blocked | A prerequisite is unmet | Evidence appears (re-checked on new events) or owner terminates |
| building | Prerequisites met; agent started with context pack | Agent returns schema-valid artifacts, or raises a clarification |
| awaiting\_clarification | Agent or reviewer needs information it cannot find in the intake, ledger or grounding sources; questions sent to the addressed role | Human answers (back to building), or round limit or clarification SLA exceeded (escalated) |
| checking | Artifacts produced | All blocking checks pass (else back to building, counted as auto-retry) |
| reviewing | Checks pass | Reviewer recommendation recorded, or reviewer raises a clarification |
| awaiting\_sign\_off | Recommendation recorded | Required approvals collected |
| escalated | Rework count > limit, SLA breach, clarification limit or SLA exceeded, or agent budget exceeded | Human completes the artifacts; then awaiting\_sign\_off |
| closed | Outcome decided | Terminal (state final); ledger record and event written |

Clarifications are not rework: the rework counter and routing are untouched. Limits come from the terminal spec `timeline` block: `clarification_sla` and `max_clarification_rounds` (proposed default 2). Agents must try grounding first and state where they looked.

### 6.3 Event model and routing

- **Events** follow `<source>.<outcome>[.<qualifier>]` from the shared event catalogue (e.g. `T4.rework.implementation`, `T8.event.drift`, `T9.reentry.T2`). Each carries use case, correlation and causation ids, and ledger references, never artifacts.
- **Outbox:** the ledger record and the outcome event are written in one transaction; a poller (with LISTEN/NOTIFY) delivers events to the router.
- **Router:** looks up the subscription view built from pinned specs' `trigger.on`; drops duplicates by event id; allows one active run per use case per terminal (a new event for an active run is delivered to it as a signal).
- **Routing resolution:** pass and exception follow the spec route; rework uses `route_by_root_cause` with the root cause tagged by the human; T8 events follow `event_routes`; T9 re-entry follows the change class.
- **Context on reroute:** the new run's context pack includes the triggering evidence (defect log, owner comment, previous artifacts), so the agent fixes rather than rebuilds.

### 6.4 Reliability

| Concern | Mechanism |
| --- | --- |
| Long human waits | Durable workflow state; runs sleep until an approval signal |
| Process restart | Workflow resumes from its last checkpoint |
| Duplicate events | Idempotency table keyed by event id |
| Undeliverable events | Retries with backoff; dead-letter after 5 attempts with an alert to the CoE |
| Ordering | Events processed in order per use case |

Editable source: page 3 of `adlc-solution-architecture.drawio`.

## 7. Agent architecture

The platform runs eleven lifecycle agents: one per terminal plus the common reviewer. All share one runtime pattern, so a new terminal agent is a registry entry, a prompt and playbooks, not new framework code.

### 7.1 Lifecycle agents

| Agent | Main job | Subagents in MVP | Model tier |
| --- | --- | --- | --- |
| T0 intake agent | Intake card, suitability, value, risk tier, RACI | None (single agent with rubric playbooks) | reasoning |
| T1 requirements agent | Requirements, applicable metrics, thresholds, KPIs, autonomy levels | None | reasoning |
| T2 architect agent | Design contract, tool contracts, token budget | None | reasoning |
| T3 builder agent | Code, prompts, tools, pipeline for the pilot agent | Up to 2 (e.g. agent implementer, harness integrator) | coding |
| T4 evaluation agent | Golden set, test runs, judging, regression pack | Judge as a separate call | reasoning |
| T5 assurance agent | Security, privacy, RAI tests and residual risk register | None | reasoning |
| T6 readiness agent | Evidence chain check, runbook, rollout plan | None | standard |
| T7 deployment agent | Simulated rollout, smoke validation, registration | None | standard |
| T8 operations agent | Monitor evaluation, periodic health report, events | None | standard |
| T9 evolution agent | Change classification, re-entry plan, retirement checklist | None | reasoning |
| Common reviewer agent | Scores checklist items, recommends an outcome | None | reasoning |

### 7.2 Runtime pattern (every terminal)

1. **Context assembly.** The orchestrator builds a context pack: terminal spec (resolved for the use case), use-case profile, prior ledger evidence named in prerequisites, trigger evidence (e.g. defect log and owner comment on rework), playbooks for this agent.
2. **Grounding.** Read-only MCP tools give access to enterprise knowledge within the spec's grounding scope; retrieved passages are cited in the artifacts. If required information is still missing, the agent raises a clarification (section 6.2) stating where it looked, instead of guessing.
3. **Structured output.** The agent must return artifacts matching the column schemas in `evidence.artifacts`; output is schema-validated before anything else sees it, and invalid output is returned to the agent automatically.
4. **Bounded execution.** Each agent run has a step limit, a token budget and a timeout from configuration; breaching them ends the run as escalate.
5. **Reviewer separation.** The reviewer agent receives only the spec checklist, the artifacts and the ledger slice, never the builder's reasoning, so its judgement is independent and reproducible.

### 7.3 Registries

| Registry | Holds | MVP form |
| --- | --- | --- |
| Lifecycle agent registry | Agent id, version, system prompt ref, tool bindings, model tier | Folder in repo + table |
| Prompt registry | Versioned prompts and instructions (lifecycle agents and pilot agent) | Folder in repo, hash recorded per run |
| Playbook registry | Versioned procedures, hashed | Table populated on spec release |
| Model catalogue | Model tier → approved model, version, fallback | Shared YAML |
| MCP / tool registry | Approved MCP servers and scopes | Shared YAML |

### 7.4 Guardrails on lifecycle agents

- Documents read through grounding are treated as data, not instructions; the system prompt states this, and tool outputs are wrapped and labelled.
- Agents cannot set outcome statuses; they can only produce artifacts.
- Every tool call passes the policy engine (section 9).
- Lifecycle agents are evaluated themselves: a fixed set of reference use cases is replayed after any prompt, playbook or model change, comparing artifact quality and reviewer agreement with the previous version.

## 8. Human-in-the-loop and experience layer

Humans act through one web application that combines the approval inbox and the lifecycle dashboard, so a decision taken in the inbox is visible on the journey view seconds later. Humans never edit specs or ledger records directly; every action goes through the orchestrator's approval API and is logged.

### 8.1 Human actions

| Action | Who | Where | Effect |
| --- | --- | --- | --- |
| Submit use case | Business owner | Intake form (free text) | Emits `usecase.submitted`; T0 opens |
| Answer a clarification | Role addressed by the agent (default the terminal's R, else A) | Inbox → clarification form | Answer added to the agent's context; the same run resumes; not counted as rework |
| Review and sign off | Terminal owners (`sign_off.roles`) | Inbox → run detail | Pass / rework / exception / terminate; reviewer recommendation shown alongside |
| Edit an artifact before approving | Terminal owners | Run detail, artifact editor | New artifact version marked `human`; drives the human edit rate KPI |
| Reject with comment and root cause | Terminal owners | Sign-off form | Mandatory comment and root cause; routed per outcome model |
| Complete an escalated terminal | Accountable owner | Escalation form | Human completes artifacts; then normal sign-off |
| Approve or reject a waiver | Waiver approver / risk owner | Waiver form | Exception recorded with owner, expiry, compensating control |
| Approve a stage inside a run | Service owner (T7) | Inbox | Releases the next rollout stage |

### 8.2 Design rules

- The sign-off screen always shows: artifacts, automated control results, reviewer findings and recommendation, prior rework comments, and the timer state.
- A human decision that differs from the reviewer recommendation requires a short reason; this feeds the reviewer–human agreement KPI.
- Notifications for MVP: in-app inbox plus email; Teams or ServiceNow approvals later use the same approval API.
- Every human action writes a `RUN_ACTIVITY` row and a `SIGN_OFF` row where applicable.

## 9. Policy, governance and controls

Every rule that can be computed is enforced by a deterministic policy engine, outside the models. Agents are judged by the reviewer agent and decided on by humans, but they cannot bypass a policy, because policies are checked on every action and at every gate.

| Concern | Mechanism | Enforced by | When |
| --- | --- | --- | --- |
| Entry conditions | Spec `prerequisites` as CEL expressions or named predicates | Policy engine | Run open |
| Permissions | Terminal-level allow / deny (deny wins), run-scoped | Policy engine + identity service | Every tool call |
| Data access | `data_access.max_class` vs data source label | MCP servers / data gateway | Every data read |
| Automated controls | CEL rules over artifacts and resolved parameters; blocking or advisory | Policy engine | After agent build, every attempt |
| Judgement checks | Spec checklist items scored with findings | Reviewer agent | After controls pass |
| Outcome rights | Fixed status rights: agent none, reviewer recommends, humans decide, orchestrator escalates | Orchestrator | Decide |
| Sign-off | Roles and minimum approvers per terminal | Approval service | Decide |
| Waivers | Owner, expiry, compensating control; rechecked at T6, monitored at T8 | Orchestrator + T6/T8 controls | Exception and later terminals |
| Separation of duties | Builder, evaluator and deployer have disjoint write permissions | Spec validation + policy engine | Spec release and run time |
| Evidence integrity | Content hashes; package hash bound T3→T7 | Orchestrator + T6/T7 controls | Close and release |

**Policy engine (MVP):** a small service wrapping a CEL evaluator and the predicate catalogue. It exposes `evaluate(rule, context)` and `authorize(actor, action, resource)`, logs every decision with inputs, and returns a reason on refusal. OPA or Cedar can replace it later behind the same two calls.

**Governance roles:** the ADLC CoE owns specs, guardrails, catalogues and the reviewer checklists; terminal owners approve changes to their terminal; an ADLC governance board approves major changes and new terminals.

## 10. Data architecture

All platform state lives in one Postgres database plus an object store for large artifacts. The database has four schemas so that ownership and access stay clear as the platform grows.

| Schema | Tables (MVP) | Written by | Read by |
| --- | --- | --- | --- |
| `spec` | spec\_registry, spec projection tables (trigger, outcome route, timeline first), playbook\_registry, usecase\_spec\_pin | Release job; orchestrator (pins) | Orchestrator, router, policy engine |
| `run` | usecase, terminal\_run, run\_activity, prerequisite\_result, control\_result, checklist\_result, run\_artifact (versioned), sign\_off, waiver, clarification | Orchestrator, policy engine, agents (via orchestrator), approval API | Orchestrator, dashboard |
| `ledger` | ledger\_record (append-only), usecase\_profile (versioned ledger artifact) | Orchestrator only | All terminals, auditors |
| `events` | outbox\_event, processed\_event (idempotency) | Orchestrator | Router |
| (object store) | Artifact files, packages, datasets, reports, keyed by content hash | Agents via orchestrator | Agents, dashboard |

**Key data rules**

- **Immutability.** Ledger records and registered spec versions are never updated. Corrections are new records; database roles enforce this.
- **Atomic close.** A terminal's ledger record and its outcome event are written in one transaction (outbox pattern), so an outcome never exists without its event.
- **Hash chain.** Each ledger record stores the content hashes of its artifacts, the spec version hash and the hash of the previous ledger record for the same use case, making tampering detectable.
- **Artifact versions.** `run_artifact` keeps the agent-produced version and every human-edited version, so the dashboard can measure human edits.
- **Use-case profile.** Stored as a versioned ledger artifact (FR-07); runs read the version current at run open and record it.
- **Activity.** `run_activity` holds one row per step per run (actor type, actor id, step, start, end, outcome); it is the source for the activity feed and time KPIs. Clarifications are stored per round (questions, addressee, answers, timestamps) and included in the run's ledger record, because they shaped the artifacts.
- **Classification.** MVP data is synthetic; the schema still labels every dataset and artifact with a data class so access ceilings work unchanged when real data arrives.
- **Retention.** Defaults per risk tier, applied by a nightly archival job; values to be confirmed (section 20).

The spec model and the runtime entity details are defined in Annex B and Annex C of the Terminal Design Specification; this architecture adds `run_activity`, artifact versioning, `usecase_profile` and the guardrail and metric catalogues.

## 11. Security architecture

The platform is itself an agentic system with write access to code, environments and evidence, so it is secured on the same principles it enforces: least privilege per run, deny by default, and no trust in content the agents read.

| Area | MVP design | Target state |
| --- | --- | --- |
| Human identity | SSO via OIDC (or local accounts in the demo environment); roles mapped from the role catalogue | Enterprise IdP groups mapped to roles |
| Agent identity | One service identity per lifecycle agent; the orchestrator issues a short-lived, run-scoped token carrying terminal, use case, permissions and data ceiling | Workload identity federation; per-subagent tokens via token exchange |
| Authorisation | Policy engine `authorize()` on every tool call; deny wins; refusals logged | Same, with OPA or Cedar |
| Secrets | Environment-injected secrets from a vault (or encrypted env file for the demo); never in specs, prompts or logs | Enterprise vault with rotation |
| Data protection | Synthetic data only; data class labels enforced at MCP servers; logs and traces masked before storage | DLP scanning, field-level encryption for restricted data |
| Prompt injection (lifecycle agents) | Grounded documents and tool outputs labelled as untrusted data; agents cannot change statuses or permissions; actions gated by policy, not by model judgement | Content scanning on ingestion; injection test suite for lifecycle agents |
| MCP server trust | Only servers in the MCP registry; each runs with its own credentials and scopes | Signed server manifests, network isolation per server |
| Integrity | Content hashes on specs, playbooks, artifacts and ledger chain | Signed specs and evidence |
| Network | Single private network for platform services; only the web app exposed | Segmented zones; private model endpoints |
| Audit | Every human action, agent tool call, policy decision and event persisted with actor and timestamp | Forwarded to enterprise SIEM |

**Platform threat model (top items):**

| Threat | Mitigation |
| --- | --- |
| An agent approves its own work | Agents hold no outcome rights; sign-off only through the approval API with human identity |
| A grounded document instructs an agent to skip a control | Controls run in the policy engine regardless of agent output |
| A deployer deploys an untested build | Deploy permission only with the package hash authorised at T6 |
| Evidence altered after approval | Append-only ledger, hash chain, no update rights for any role |
| Spec changed to weaken a control without review | CODEOWNERS, validation rules, version and hash pinned per use case |

## 12. Observability and lifecycle dashboard

Observability has two audiences. Lifecycle observability shows humans how the use case is progressing; platform observability shows engineers whether the platform is healthy. Both come from data the platform already writes, so no separate instrumentation of the lifecycle is needed.

### 12.1 Telemetry sources

| Source | Content | Used for |
| --- | --- | --- |
| `run_activity` | One row per step per run: actor, step, start, end, outcome | Activity feed, time split, escalation points |
| Run tables | Terminal runs, sign-offs, control and checklist results, waivers | Journey, KPIs |
| `outbox_event` | Every routing event with causation | Reroute arrows on the journey |
| Agent traces | LLM calls, tool calls, tokens, latency per agent run, tagged with `run_id` | Run detail drill-down, lifecycle agent cost |
| Service metrics and logs | Orchestrator, router, policy engine, web app health | Platform health alerts |

### 12.2 Dashboard (MVP)

| View | Content |
| --- | --- |
| Lifecycle journey | T0–T9 track: runs per terminal, status, time, current owner (agent, reviewer, human); arrows for rework, cross-terminal reroutes, exceptions and T9 re-entry; KPI strip; escalations and exceptions panel |
| Terminal run detail | Step timeline, artifacts (agent vs human versions), control results, reviewer findings, human decision and comment, timers |
| Activity feed | Chronological agent, reviewer, human and orchestrator actions, filterable |
| Human inbox | Pending sign-offs, escalations, waivers with due time |

### 12.3 MVP KPIs

| KPI | Definition |
| --- | --- |
| Lifecycle elapsed time | T0 open to T9 close, or now |
| Time per terminal, split | Agent working, reviewer, waiting for clarification, waiting for sign-off |
| Reworks per terminal | Count by root cause |
| Clarifications per terminal | Count of clarification rounds, with the addressed role |
| Clarification wait time | Time from question to answer, per terminal |
| First-pass yield | Share of terminals passed on first run |
| Escalations | Count, with terminal, run and trigger (rework limit, clarification limit or SLA) |
| Reviewer–human agreement | Share of decisions matching the reviewer recommendation |
| Human edit rate | Share of agent artifacts changed by humans before approval |
| Control first-time pass rate | Share of blocking controls passed on first attempt |
| SLA adherence | Terminals closed within expected duration |
| Open exceptions | Active waivers with expiry and T6 recheck result |
| Lifecycle agent cost | Tokens and cost per terminal |
| T8 health | Pilot eval score vs T4 baseline, cost per task, events raised |

Each KPI is a Postgres view; the web app polls them every few seconds (NFR-04). Agent tracing uses OpenTelemetry-compatible tooling (Langfuse or LangSmith; decision in section 17), linked by `run_id`.

## 13. Integration architecture

All external systems are reached through MCP servers (for agents) or adapters (for platform services), each behind a stable interface. For the MVP, systems not yet available are mocked behind the same interface, so moving to the real system changes configuration, not platform code (P-9).

| Integration | Used by | Interface | MVP | Target |
| --- | --- | --- | --- | --- |
| Enterprise knowledge (Confluence, SharePoint, wiki) | T0–T2, T5 agents (grounding) | MCP read-only | Real if access available; otherwise local document folder MCP | Real MCP servers |
| Source control (Git) | T3 agent, spec CI | MCP (branch write, PR) + Git API | Real (platform Git host) | Same |
| CI pipeline | T3 agent | MCP (run pipeline, read results) | Real (repo CI) | Enterprise CI |
| Model providers | All lifecycle agents, pilot agent | Model gateway (one API, model catalogue) | One provider via gateway | Multiple providers, private endpoints |
| Eval harness | T4, T8 agents | MCP (run suite, read results) | Platform-hosted harness | Same, shared service |
| Red-team harness | T5 agent | MCP | Platform-hosted test suite | Enterprise red-team tooling |
| ITSM (change, incident) | T6, T7, T8 | Adapter + MCP | Mock (records in platform DB) | ServiceNow |
| CMDB / enterprise agent registry | T7, T9 | Adapter + MCP | Platform table | Enterprise CMDB or AI inventory |
| Deployment target | T7 agent | MCP (deploy hash, set traffic split, rollback) | Simulated: containers in the demo environment | Enterprise CD and runtime platform |
| Telemetry of pilot agent | T8 agent | MCP (query metrics, traces) | Platform tracing + synthetic traffic | Enterprise observability |
| Notifications | Approval service | Adapter | In-app + email | Teams, ServiceNow approvals |
| Identity | All | OIDC | Demo IdP or local accounts | Enterprise IdP |

**Integration rules:** every MCP server is listed in the MCP registry with owner and scopes; mocks implement the same tool names and schemas as the real server; adapters are idempotent and retried through the outbox.

## 14. Pilot use case execution environment

The pilot, the Travel Claims Assistant, is the agent the platform builds, tests, deploys and operates. It runs in its own environments, separate from the platform, so the platform treats it exactly as it would any team's agent.

| Environment | Purpose | Used by | Data |
| --- | --- | --- | --- |
| Pilot dev | Build and unit test the pilot agent | T3 builder agent | Synthetic |
| Pilot test | Evaluation and assurance against the immutable candidate | T4, T5 agents | Synthetic golden set, planted test PII |
| Pilot prod-sim | Simulated production: shadow / canary / full rollout as container replicas behind a traffic splitter | T7, T8 agents | Synthetic live traffic |

**Supporting services (MVP)**

- **Synthetic data generator:** produces claims (trip delay, baggage) with personas and edge cases from the T1 scenarios; used for the T4 golden set and T8 traffic.
- **Traffic generator:** sends a steady stream of synthetic claims to prod-sim so T8 monitors have data.
- **Fault injector:** triggers scripted events for the demo, e.g. a model version swap that lowers the online eval score (drift → T9 → re-entry at T2), or a planted PII leak (safety event → T5).
- **Simulated ITSM:** records change requests and incidents in the platform database through the ITSM adapter.

**Pilot agent shape:** one agent (claims triage and response), optionally a second (document check). It uses 2–3 mocked tools (policy lookup, claim status, baggage tracker), emits traces and RAI metrics, and enforces its token budget, as required by its own T2 design contract.

## 15. Deployment and infrastructure

The MVP runs as containers on one host, defined in a single versioned Compose file. Every service is a container image built in CI, so moving to Kubernetes later reuses the same images and configuration.

&#91;embedded content: deployment view (MVP) · one host, three container groups, four external systems\]

| Container group | Services | Notes |
| --- | --- | --- |
| Platform services | Web app (FastAPI + React), orchestrator and router, policy engine, agent workers, model gateway, MCP servers (real and mocked) | Stateless; state lives in PostgreSQL and the object store |
| Data | PostgreSQL (spec, run, ledger, events schemas), MinIO object store, Langfuse tracing | Nightly backup of PostgreSQL and object store |
| Pilot environments | Pilot dev, pilot test, prod-sim with traffic splitter, traffic generator, fault injector | Separate container network; reached by agents only through MCP servers |

**Platform environments:** `dev` (engineers, mocks everywhere) and `demo` (stable, used for the MVP demo). Spec releases target both registries; platform releases are image tags promoted from dev to demo.

**Path to target state**

| Concern | MVP | Target |
| --- | --- | --- |
| Runtime | Docker Compose, one host | Kubernetes, one namespace per environment; pilot workloads in their own namespaces |
| Database | PostgreSQL container | Managed PostgreSQL with HA and point-in-time recovery |
| Events | Outbox poller | Outbox + CDC to Kafka for multiple consumers |
| Infrastructure as code | Compose file in repo | Terraform or equivalent for clusters, databases, networks |
| Secrets | Encrypted env file or vault | Enterprise vault with rotation |
| Availability | Restart policies | Multiple replicas, zone redundancy |

Editable source: page 4 of `adlc-solution-architecture.drawio`.

## 16. Quality attributes

| Attribute | MVP target | How achieved | Target state |
| --- | --- | --- | --- |
| Auditability | 100% of decisions, checks and events traceable to spec version, actor and evidence hash | Ledger hash chain, run\_activity, outbox | Signed evidence, SIEM export |
| Reliability | No lost or duplicated lifecycle events; runs resume after restart | Durable workflow checkpoints, outbox, idempotent router | HA database, multi-instance orchestrator |
| Availability | Demo environment available during working hours | Single host, restart policies | 99.5% for platform services |
| Performance | Routing ≤ 2 s after outcome; dashboard refresh ≤ 10 s | Indexed views, polling | Streaming, read replicas |
| Scalability | One use case end to end; up to 3 in parallel without code change | Stateless services, run concurrency keyed by use case | Hundreds of use cases; queue-based workers |
| Cost | Lifecycle agent tokens per terminal visible; pilot run cost known | Tracing, token budgets per agent run | Per-use-case budgets and alerts |
| Maintainability | Lifecycle changes by spec PR only | Spec-driven design, schema validation | Authoring UI, typed config language |
| Extensibility | New metric, control, approver or guardrail with no platform code change | Catalogues, applicability, generic controls | New terminal or integration with no code change |
| Security | No agent holds outcome rights; all tool calls policy-checked | Run-scoped tokens, policy engine | Per-subagent tokens, enterprise IAM |
| Usability | An owner completes a sign-off in under 5 minutes from the inbox | Single app, structured artifacts, reviewer summary | Role-based views, mobile approvals |

## 17. Technology stack and architecture decisions

Choices below are **proposed** for the MVP and need confirmation (ADR status). Each sits behind an interface so it can be swapped as the platform scales.

| Component | MVP choice (proposed) | Alternatives | Rationale | Swap boundary |
| --- | --- | --- | --- | --- |
| Spec format | YAML + JSON Schema + CEL | CUE / Pkl, BPMN | Readable by owners, Git-reviewable, validatable | Registry stores JSON; source format can change |
| Workflow / orchestration | PostgreSQL state machine (one row per run, one transaction per signal); LangGraph for agent graphs only. Changed by feature 003 (CoE to confirm) | LangGraph with Postgres checkpointer, Temporal, Camunda | One copy of run state; the close writes the run, ledger record and outcome event atomically; restart safety from the database | Terminal-run state machine interface (`TerminalRun`) |
| Lifecycle agents | Python agents on the same framework; model via gateway | Claude Agent SDK, other agent SDKs | One runtime pattern for all terminals | Agent registry entry + context pack contract |
| Model access | One model gateway with model catalogue (tiers) | Direct provider SDKs | Central model swap, cost tracking | Model tier names |
| Policy engine | CEL evaluator + predicate catalogue in a small service | OPA / Rego, Cedar | Fast to build; expressive enough | `evaluate()` and `authorize()` |
| Database | PostgreSQL (ledger, runs, specs, outbox) | Separate stores per concern | One store keeps MVP simple and transactional | Schema-per-concern |
| Object store | S3-compatible (MinIO locally) | Cloud blob storage | Content-addressed artifacts | Storage adapter |
| Event delivery | Postgres outbox + poller (+ LISTEN/NOTIFY) | Kafka, cloud event bus | No extra broker for MVP | Router interface; CDC to Kafka later |
| Tool integration | MCP servers (real or mocked) | Direct API clients | One protocol for all agent tools | MCP registry |
| Web app | FastAPI backend + React frontend | Streamlit, Grafana for KPIs | One app for inbox and dashboard; demo polish | Approval and query APIs |
| Tracing | Langfuse (self-hosted) or LangSmith | OpenTelemetry + Grafana Tempo | Agent-aware traces, token cost | OTel-compatible export |
| Packaging and runtime | Docker Compose on one host | Kubernetes | Fast to stand up | Container images unchanged |
| CI | Git host CI (e.g. GitHub Actions) | GitLab CI, Jenkins | Spec validation and release jobs | `adlc-spec` CLI |

**Decisions to record as ADRs:** ADR-01 workflow engine; ADR-02 agent framework and model provider; ADR-03 policy language; ADR-04 single Postgres vs split stores; ADR-05 web stack; ADR-06 tracing tool; ADR-07 hosting target.

## 18. Extensibility and roadmap

Extensibility is designed in through configuration and stable interfaces, so each later phase adds capability without reworking the MVP core.

### 18.1 Extension points

| Extension | Mechanism | Platform code change |
| --- | --- | --- |
| New metric, KPI or threshold | Metric catalogue entry; use-case profile value | None |
| New control or checklist item | Terminal spec + policy predicate if new | None, or one predicate |
| New approver, sign-off rule or role | Spec + role catalogue | None |
| Tighter enterprise limit | Guardrails file | None |
| New terminal | Spec + agent registry entry + prompt and playbooks | None for orchestration; new agent configuration |
| New integration | MCP server registered in the MCP registry | New MCP server only |
| Swap a mock for a real system | Same MCP tool names and schemas, new endpoint | Configuration only |
| New model or provider | Model catalogue entry behind the gateway | None |
| Workflow engine, policy engine or event bus swap | Behind `terminal run`, `evaluate/authorize` and router interfaces | Adapter only |
| Runtime move to Kubernetes | Same images and configuration | Deployment manifests only |

### 18.2 Roadmap

&#91;embedded content: roadmap · 4 phases, 3 gates\]

**Gate criteria:** *MVP demo accepted* = D-1 to D-9 shown, acceptance criteria in section 21 met. *Pilots onboarded* = 3–5 use cases from at least two teams running on one spec bundle without platform code changes. *Scale review* = KPIs show reduced lifecycle effort with stable or better assurance outcomes.

Editable source: page 5 of `adlc-solution-architecture.drawio`.

## 19. Operating model touchpoints

| Role | Responsibility toward the platform | MVP holder |
| --- | --- | --- |
| ADLC CoE | Owns specs, guardrails, catalogues, playbooks, reviewer checklists; runs spec releases; tracks lifecycle KPIs | Framework lead + 1–2 engineers |
| Platform engineering | Builds and operates orchestrator, agents runtime, policy engine, ledger, web app, CI | Platform team |
| Terminal owners | Sign off terminal runs; approve changes to their terminal spec | Named people for the pilot per T0 RACI |
| ADLC governance board | Approves major spec changes, new terminals, guardrail changes | CoE lead + security, RAI, architecture leads |
| Use-case team | Submits the use case, supplies business context, owns the pilot agent's value | Pilot business owner and product owner |
| Support | Responds to platform incidents and stuck runs (dead-letter events, escalations not picked up) | Platform team during MVP |

**Onboarding a use case (target state):** business owner submits at T0 → RACI resolved to named people → profile set at T0–T2 → lifecycle runs on the active spec bundle. No platform change is needed per use case.

## 20. Risks, assumptions, dependencies and open decisions

**Risks**

| # | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| R-1 | Ten terminal agents plus platform is too much for the timeline | MVP slips | Build one runtime pattern first; thin agents with strong playbooks; T6/T7 agents mostly deterministic |
| R-2 | Lifecycle agent output quality too low for owners to accept | Many reworks; weak demo | Narrow artifact schemas; good playbooks; reviewer catches gaps before humans |
| R-3 | Owner availability for sign-offs during demo | Demo stalls | Named owners and back-ups; compressed timers; escalation path visible |
| R-4 | T3 agent cannot build the pilot agent reliably | Lifecycle blocks at T3 | Golden template for the pilot; allow human-assisted build via escalation (counts as a demo point) |
| R-5 | Model or provider limits or cost | Delays | Model gateway with fallback; token budgets |
| R-6 | Simulated T7/T8 seen as unrealistic | Credibility | Real containers, real traffic splitting, scripted but genuine faults |

**Assumptions:** A-1 synthetic data is acceptable for the MVP; A-2 named owners exist for each terminal; A-3 one model provider is approved for MVP; A-4 Git host and CI are available to the platform.

**Dependencies:** model provider access; Git and CI; access to enterprise knowledge sources (or approval to use a local document set); a host for the demo environment.

**Open decisions**

- [ ] Spec permission vs tool scope overlap: keep permissions only and derive tool scopes through `permission_tool_map`
- [ ] Apply the superset principle, guardrails, metric catalogue and use-case profile to the Terminal Design Specification
- [ ] Apply the parameters change (six thresholds) to the specification
- [ ] Add `clarification_sla` and `max_clarification_rounds` to the specification's `timeline` block and base template
- [ ] Convert free-text conditions into named predicates
- [ ] Subagent-level permissions (post-MVP)
- [ ] Data classification mapping to the enterprise scheme
- [ ] Regulations in scope for T5
- [ ] Ledger retention per risk tier
- [ ] Hosting target (ADR-07) and the ADR-01 to ADR-06 technology choices
- [ ] Spec bundles vs per-terminal pinning

## 21. Validation and demo plan

**Demo scenario (one session, compressed timers)**

| Step | Terminal | What happens | Proves |
| --- | --- | --- | --- |
| 1 | T0 | Business owner submits the Travel Claims use case; agent builds the intake card; owner passes it; risk tier set | D-1 |
| 2 | T1 | Agent proposes requirements and profile; owner rejects with comment (KPI baseline missing); agent reworks; pass | D-1, D-2 |
| 3 | T2 | Agent asks one clarification (claim data retention period); owner answers; same run resumes; design contract passes | D-1, D-9 |
| 4 | T3 | Builder agent produces the pilot agent and candidate package hash | D-1, D-6 |
| 5 | T4 | Evaluation finds a tool-timeout defect; rework routed to T3 (root cause: implementation); T3 run 2; T4 pass | D-3 |
| 6 | T5 | A log-masking gap is accepted as an exception with waiver | D-5 |
| 7 | T6 | Readiness verifies the evidence chain, hash match and waiver; release authorised | D-5, D-6 |
| 8 | T7 | Simulated canary then full rollout of the authorised hash; smoke pass; handover | D-6 |
| 9 | T8 | Synthetic traffic runs; fault injector swaps the model; drift event raised | D-7 |
| 10 | T9 | Change classified as moderate; re-entry at T2 (shown) or retirement checklist | D-7 |
| (any) | — | One terminal is driven to escalation by repeated rejection to show D-4 | D-4 |
| Throughout | Dashboard | Journey, reroutes, clarifications, activity, time split and KPIs update live | D-8 |

**Platform test strategy**

| Level | Scope |
| --- | --- |
| Spec tests | All specs pass `adlc-spec validate`; event graph and evidence references complete |
| Unit | Policy engine rules and predicates; routing resolution; parameter resolution; hash chain |
| Integration | Orchestrator ↔ policy engine ↔ ledger ↔ outbox ↔ router; approval API; MCP mocks |
| Agent quality | Each lifecycle agent against 2–3 reference use cases; artifact schema validity; reviewer agreement |
| End to end | Scripted lifecycle scenarios: happy path, rework, cross-terminal reroute, escalation, exception, re-entry, retirement |
| Resilience | Restart orchestrator mid-run; duplicate event delivery; dead-letter handling |

**MVP acceptance criteria:** demo moments D-1 to D-9 shown live; every decision traceable in the ledger to spec version, actor and evidence hash; all scripted scenarios pass; no agent able to set an outcome or deploy an unauthorised hash in negative tests.

## Annex A – Naming conventions

Every name in specs, catalogues, events, runtime records and the repo follows these rules; `adlc-spec validate` enforces the spec-side patterns.

### A.1 General rules

| Style | Used for | Example |
| --- | --- | --- |
| `snake_case` | YAML keys, artifact ids, columns, metrics, parameters, guardrails, predicates, roles, enum values, MCP servers, database objects | `eval_thresholds`, `qa_eval_lead` |
| `kebab-case` | Agent and subagent ids, file names, Git branches | `t3-builder-agent`, `t0-intake.md` |
| `UPPER-CODE-nn` | Check, playbook, monitor and record ids | `CTL-T3-02` |
| Dot-separated | Events, evidence references, template paths | `T4.rework.implementation` |
| Colon-separated | Permissions and tool scopes | `write:repo.feature_branch` |
| Semver (quoted in YAML) | Spec, playbook, guardrail and bundle versions | `"1.1.0"` |

Names are English, singular nouns for entities, at most 40 characters, with no abbreviations other than RAI, KPI, SLA, PII, PHI, MCP, CI, CD.

### A.2 Spec identifiers

| Element | Pattern | Example |
| --- | --- | --- |
| Terminal id | `T<n>` | `T3` |
| Terminal spec file | `specs/terminals/T<n>.yaml` | `specs/terminals/T3.yaml` |
| Prerequisite | `PRE-T<n>-<nn>` | `PRE-T3-04` |
| Automated control | `CTL-T<n>-<nn>` | `CTL-T3-02` |
| Checklist item | `CHK-T<n>-<nn>` | `CHK-T3-04` |
| Playbook | `PB-T<n>-<nn>`; shared `PB-SH-<nn>` | `PB-T0-02` |
| Grounding source | `GR-T<n>-<nn>` (generated by the loader) | `GR-T5-01` |
| Monitor (T8) | `MON-<nn>` | `MON-04` |
| Validation rule | `V-<nn>` | `V-05` |
| Terminal agent | `t<n>-<function>-agent` | `t4-evaluation-agent` |
| Reviewer agent | `common-terminal-reviewer` | — |
| Subagent | `<function>` noun phrase, unique within the terminal | `prompt-engineer` |
| Artifact | `<noun>` | `build_manifest` |
| Artifact column | `<noun>[_<unit>]`; units `_pct`, `_ms`, `_usd`, `_count` | `p95_latency_ms` |
| Evidence reference | `T<n>.<artifact>[.<field>]`, or `<source>.<field>` for intake, env, change, template, dataset, trigger | `T3.candidate_package.sha256` |
| Template variable | `${<path>}`; parameters `${param.<name>}`; tier values `tier.<param>` | `${T1.eval_thresholds.task_success_rate}` |
| Ledger key | `<usecase_id>/T<n>/<run_version>`; T8 `<usecase_id>/T8/<review_period>` | `UC-0042/T3/run-2` |

### A.3 Events and routing values

| Element | Pattern | Example |
| --- | --- | --- |
| Terminal outcome | `T<n>.<status>` | `T2.pass` |
| Rework | `T<n>.rework.<root_cause>` | `T4.rework.implementation` |
| Re-entry | `T9.reentry.T<n>` | `T9.reentry.T2` |
| Operational event | `T8.event.<event_name>` | `T8.event.drift` |
| Rollback | `T7.rollback` | — |
| External event | `<domain>.<past-tense verb>` (or `<state>_due`) | `usecase.submitted`, `lifecycle.review_due` |
| Outcome status, root cause, change class, risk tier | lowercase `snake_case` word from the shared enumeration | `control_missing`, `moderate` |

### A.4 Authorities and catalogues

| Element | Pattern | Example |
| --- | --- | --- |
| Permission | `<verb>:<resource>[.<qualifier>]`; verbs from a fixed list (read, write, merge, run, invoke, deploy, provision, approve, accept, revoke, activate, archive, disable, set, raise) | `deploy:outside_window` |
| Tool scope | `mcp:<server>:<scope>` | `mcp:git:branch_write` |
| MCP server | `<system>` | `servicenow`, `eval_store` |
| Role | `<function>_<title>` | `security_officer` |
| Data class, model tier | lowercase word or `snake_case` | `confidential_masked`, `reasoning` |
| Predicate | `<verb or adjective>[_<object>]` | `within_window`, `exists` |
| Metric | `<measure>[_<qualifier>]`, ratios end `_rate`, units as for columns | `task_success_rate`, `cost_per_task_usd` |
| Parameter / guardrail | `<measure>_<min or max>` | `unit_coverage_min`, `injection_success_max` |

### A.5 Use-case and runtime identifiers

| Element | Pattern | Example |
| --- | --- | --- |
| Use case | `UC-<nnnn>` | `UC-0042` |
| Run version | `run-<k>`, incremented per use case per terminal | `run-2` |
| Run id | `<usecase_id>/T<n>/<run_version>` | `UC-0042/T3/run-2` |
| Event id | UUID v7 (time-ordered) | — |
| Correlation / causation id | `<usecase_id>/lifecycle` / the causing run id | `UC-0042/lifecycle` |
| Clarification round | `<run_id>/clar-<k>` | `UC-0042/T2/run-1/clar-1` |
| Waiver | `WVR-<nnnn>` | `WVR-0007` |
| Requirement ids (T1 artifacts) | `FR-<nn>`, `NFR-<nn>`, `BEH-<nn>`, `SC-<nn>` (scenario), `KPI-<nn>` | `NFR-03` |
| Design decision (T2) | `DD-<nn>` | `DD-07` |
| Defect, threat, residual risk | `DEF-<nnn>`, `THR-<nn>`, `RSK-<nn>` | `DEF-118` |
| Content hash | `sha256:<hex>` | — |
| Object store key | `adlc-artifacts/sha256/<hex>` (content-addressed) | — |
| T8 review period | `YYYY-MM-DD` (period start) | `2026-12-01` |

### A.6 Repository, Git and database

| Element | Pattern | Example |
| --- | --- | --- |
| Playbook file | `specs/playbooks/t<n>-<topic>.md`; shared `specs/playbooks/shared/<topic>.md` | `t0-intake.md` |
| Checklist file | `specs/checklists/t<n>.yaml` | `t3.yaml` |
| Shared catalogue file | `specs/shared/<plural noun>.yaml` | `roles.yaml`, `guardrails.yaml` |
| Spec branch | `spec/<T<n> or shared>-<short-description>` | `spec/T3-add-sbom-blocking` |
| Spec release tag | `spec/<T<n> or guardrails>/<version>`; bundle `bundle/<version>` | `spec/T3/1.1.0` |
| Platform image | `adlc-<service>:<semver>` | `adlc-orchestrator:0.4.0` |
| Database schema | one lowercase word | `ledger` |
| Table | singular `snake_case`; spec projections prefixed `spec_` | `terminal_run`, `spec_control` |
| View | `v_<subject>` | `v_terminal_time` |
| Column | `snake_case`; foreign keys `<entity>_id`; timestamps `<event>_at`; booleans read as statements | `approved_at`, `schema_valid` |

**Alignment needed in the current specification:** rename `max_injection_success` and `max_jailbreak_success` to `injection_success_max` and `jailbreak_success_max`; rename `judge_human_agreement` to `judge_agreement_min` where it is a parameter; add unit suffixes to numeric artifact columns; name metrics with the `_rate` and unit suffixes (e.g. `task_success` → `task_success_rate`).
