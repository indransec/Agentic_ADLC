# Agentic ADLC MVP – Spec-Driven Build Plan (GitHub Spec Kit, Open-Source Python)

Nov 8, 2026 · @Indrajit

## 1. Approach

The MVP is built as 14 feature slices, each taken through Spec Kit from specification to implementation by an AI coding agent, with a human review gate after the spec, the plan and the tasks. The solution architecture and the Terminal Design Specification are the source material for every feature spec; Spec Kit turns them into code in small, reviewable steps.

Two kinds of "spec" exist in this project and must not be confused:

|  | Spec Kit feature specs | ADLC terminal specs |
| --- | --- | --- |
| Describe | What the **platform** must do (e.g. "the router opens one run per use case per terminal") | What a **lifecycle terminal** requires at run time (prerequisites, controls, routing) |
| Consumed by | The coding agent, to build platform code | The running platform, to drive T0–T9 |
| Format | Markdown in `specs/<nnn>-<feature>/` (Spec Kit layout) | YAML in `adlc-specs/terminals/` |
| Lifecycle | Written once per feature, kept as design record | Versioned, validated, registered, pinned per use case |

To keep them apart, the terminal specs move to an `adlc-specs/` folder (the solution architecture used `specs/`, which Spec Kit owns). Feature 002 builds the toolkit that validates and registers the terminal specs; later features consume them.

**Inputs for every feature spec:** the relevant solution architecture sections, the Terminal Design Specification (Annexes B and C), Annex A naming conventions, and the demo moments D-1 to D-9 that the feature must support.

## 2. Spec Kit workflow

Spec Kit is an open-source CLI (`specify`) plus a set of slash commands that run inside a supported AI coding agent (e.g. Claude Code, Gemini CLI, GitHub Copilot). The project uses the full path with all quality gates, because the platform's correctness matters more than speed of each slice.

**One-time setup**

```bash
uv tool install specify-cli            # or pin: --from git+https://github.com/github/spec-kit.git@vX.Y.Z
specify init agentic-adlc --integration claude --script py   # pick your coding agent; Python scripts
specify version                        # verify
```

**Per-feature flow and human gates**

| Step | Command | Input from us | Output | Human gate |
| --- | --- | --- | --- | --- |
| 0 | `/speckit.constitution` (once) | Section 3 articles | Project constitution checked by every later step | CoE lead approves |
| 1 | `/speckit.specify` | What and why: the feature's slice of the solution architecture, user stories, acceptance criteria, demo moments; **no tech stack** | Feature `spec.md` | — |
| 2 | `/speckit.clarify` | Answers to the agent's questions | Gaps resolved in the spec | **Gate 1: spec review** (architect + feature owner) |
| 3 | `/speckit.plan` | Tech stack and constraints from section 4, interfaces to earlier features | Plan and design artifacts (data model, contracts) | **Gate 2: plan review** (architect) |
| 4 | `/speckit.checklist` | Focus area (e.g. "security and audit requirements") | Requirements-quality checklist | Items ticked by reviewer |
| 5 | `/speckit.tasks` | — | Dependency-ordered `tasks.md` | **Gate 3: task review** (tech lead) |
| 6 | `/speckit.analyze` | — | Read-only report of conflicts across spec, plan, tasks | Fix before implementing |
| 7 | `/speckit.implement` | — | Code and tests, executed task by task | Code review on the PR |
| 8 | `/speckit.converge` | — | Checks code against spec, plan and tasks; appends missing tasks | Repeat 7–8 until converged; merge |

**Working rules**

- One feature = one branch (`<nnn>-<feature>`) = one pull request. Small enough to review in under an hour.
- Tech stack appears only at `/speckit.plan`, never in the spec, so specs stay valid if a tool is swapped.
- Specs reference the architecture by section number; when the architecture changes, affected feature specs are updated first, then re-planned.
- `/speckit.taskstoissues` can push tasks to GitHub Issues for tracking if the team works in parallel.

## 3. Constitution

The constitution is the first artifact Spec Kit creates; every later plan and task list is checked against it. Its articles come straight from the solution architecture principles plus engineering rules for the MVP. Paste the block below into `/speckit.constitution`.

```markdown
Agentic ADLC Platform – Constitution

I.   Spec-driven lifecycle. Lifecycle behaviour (terminals, controls, routing, approvers,
     timelines) is defined in versioned YAML terminal specs and shared catalogues.
     Platform code must not hard-code any of it.
II.  Superset, not values. Terminal specs define what must be captured. Use-case values
     come only from the use-case profile; enterprise limits only from guardrails.
III. Agents build, humans decide. Agents produce artifacts and recommendations. Only humans
     set pass, exception or terminate; only the orchestrator sets escalate.
IV.  Separation of duties by permission. Builder, evaluator and deployer capabilities are
     enforced by the policy engine and run-scoped tokens, never by prompt text alone.
V.   Evidence-first. Every terminal outcome writes an append-only, hashed ledger record and
     its next event in one database transaction. Later steps read evidence only from the ledger.
VI.  Deterministic before judgement. Anything computable is a policy-engine rule; LLM
     judgement is used only where a rule cannot decide.
VII. Interfaces at every boundary. Workflow engine, policy engine, model access, storage,
     event delivery and every external system sit behind an interface; mocks implement the
     same interface as the real system.
VIII.Open source, Python first. Python 3.12+, fully typed. Only OSI-approved licences for
     platform dependencies; licence noted in the plan for every new dependency.
IX.  Test first for the core. Policy rules, routing, parameter resolution, ledger hashing
     and run state transitions are written test-first. Every feature ships with tests
     and passes CI before merge.
X.   Observable by default. Every run step writes a run_activity row; every agent and
     tool call is traced with run_id.
XI.  Secure by default. No secrets in code, specs, prompts or logs. Deny by default.
XII. Simplicity for the MVP. Prefer the simplest design that meets the demo moments
     D-1 to D-9; anything else is recorded as post-MVP, not built.
XIII.Naming. Follow Annex A naming conventions of the solution architecture.
```

**Amendments** follow a PR to the constitution, approved by the CoE lead and the architect; open feature plans are then re-checked with `/speckit.analyze`.

## 4. Open-source Python tech stack

Every platform component is open source and, except the database, the proxy and the identity server, written in or driven from Python. Licences below are as commonly published; each feature plan re-confirms the licence of any dependency it adds (constitution VIII).

| Concern | Choice | Licence | Swap boundary / alternative |
| --- | --- | --- | --- |
| Language and tooling | Python 3.12, uv, ruff, mypy, pytest | Python PSF; MIT / Apache | — |
| API | FastAPI + Pydantic v2 | MIT | Platform API contracts |
| Workflow / orchestration | PostgreSQL state machine behind `TerminalRun` (changed by feature 003, ADR-01; CoE to confirm). LangGraph considered for agent graphs once subagents arrive (feature 006 runs a bounded loop without it) | — (own code) | `TerminalRun` interface; Temporal (MIT) later |
| Database | PostgreSQL 16; SQLAlchemy 2 + Alembic; psycopg 3 | PostgreSQL; MIT; LGPL-3.0 | Schema-per-concern |
| Event delivery | Postgres outbox + poller (LISTEN/NOTIFY) | — (own code) | Router interface; Kafka later |
| Policy engine | cel-python + predicate catalogue | Apache-2.0 | `evaluate` / `authorize`; OPA or Cedar later |
| Spec toolkit | ruamel.yaml, jsonschema, networkx, Typer (CLI) | MIT / MIT / BSD / MIT | `adlc-spec` CLI |
| Model gateway | LiteLLM (Python SDK, pinned; no proxy, router or callbacks) behind the ADLC `ModelGateway`, which owns the fallback order and records every call (feature 006) | MIT (core) | Model catalogue by tier and profile |
| Models | ADR-02 (decided 2026-11-10): commercial models through LiteLLM. Catalogue per tier, `default` profile: Anthropic first (Claude Opus 5.5 for reasoning and coding, Claude Sonnet 5.5 for standard), then OpenAI, then Gemini; fallback only on availability errors, never on refusals. `dev` profile: OpenAI GPT-4o mini first. CoE to confirm the OpenAI and Gemini ids and the data-class approvals | — | Model tier names; catalogue profiles |
| Agent tools | Official MCP Python SDK (FastMCP) for all MCP servers | MIT | MCP registry |
| Artifact storage | Local content-addressed file store behind a storage interface | — (own code) | S3-compatible later (e.g. SeaweedFS, Apache-2.0); avoid MinIO unless AGPL-3.0 is acceptable |
| UI (inbox + dashboard) | Streamlit (+ Plotly for charts; `st.data_editor` for artifact tables) | Apache-2.0; MIT | Approval and query APIs; React later if needed |
| Tracing | OpenTelemetry SDK; Langfuse self-hosted | Apache-2.0; MIT (core) | OTel export; Jaeger (Apache-2.0) if Langfuse is too heavy |
| Evaluation (T4, T8) | DeepEval, Ragas where retrieval applies | Apache-2.0 | Eval harness MCP |
| Red-team (T5) | garak, PyRIT | Apache-2.0; MIT | Red-team harness MCP |
| Synthetic data and traffic | Faker; Locust | MIT | Pilot tooling |
| Deploy simulation (T7) | Docker SDK for Python; Traefik weighted routing | Apache-2.0; MIT | Deploy and traffic MCP |
| Identity | Keycloak (OIDC); local accounts acceptable for the demo | Apache-2.0 | OIDC |
| Packaging and runtime | Docker Compose | Apache-2.0 | Kubernetes later |
| CI | GitHub Actions (with Spec Kit on GitHub) | Service | Any CI running the same `make` targets |

**Notes**

- **UI change from the solution architecture:** Streamlit replaces React for the MVP to keep the stack Python-only and save build time; the approval and query APIs stay the same, so a React UI can replace it later. Section 17 of the architecture needs this update.
- **Langfuse self-hosting** (v3) brings ClickHouse and Redis; if that is too heavy for the demo host, start with OpenTelemetry to Jaeger and token counts in `run_activity`.
- **Pilot agent** (Travel Claims Assistant) is built on the same stack (LangGraph agent, MCP tools), so the platform team owns one toolset.

## 5. Repository layout

One repository (decision from the spec governance discussion), with Spec Kit's folders, the ADLC terminal specs and the platform code clearly separated.

```
agentic-adlc/
├── .specify/                     # Spec Kit: constitution, templates, scripts (managed by specify)
├── specs/                        # Spec Kit feature specs: 001-platform-foundation/ … 014-e2e-demo/
│                                 #   spec.md, plan.md, tasks.md + design artifacts per feature
├── adlc-specs/                   # ADLC terminal specs (runtime configuration)
│   ├── terminals/T0.yaml … T9.yaml
│   ├── shared/                   # roles, events, guardrails, metric catalogue, predicates, …
│   ├── playbooks/  checklists/
│   └── schema/terminal.schema.json
├── src/adlc/                     # platform code (one Python package, modules per layer)
│   ├── spec_toolkit/             # validate, register (adlc-spec CLI)
│   ├── orchestration/            # outbox, router, workflow, timers
│   ├── policy/                   # CEL evaluator, predicates, authorize, parameters
│   ├── ledger/                   # ledger, hash chain, artifact store, run_activity
│   ├── agents/                   # runtime, context builder, gateway, reviewer, terminals/t0 … t9
│   ├── api/                      # FastAPI: intake, approvals, query
│   └── ui/                       # Streamlit: inbox, journey, run detail, activity, KPIs
├── mcp_servers/                  # knowledge, git_ci, eval, redteam, deploy, telemetry, itsm_mock
├── pilot/                        # Travel Claims golden template, synthetic data, traffic, faults
├── db/migrations/                # Alembic
├── tests/                        # unit, integration, scenario (D-1 … D-9)
├── deploy/compose.yaml           # demo host
└── .github/workflows/            # ci.yml (code), specs-ci.yml + specs-release.yml (adlc-specs)
```

## 6. Feature breakdown (build order)

Fourteen Spec Kit features, ordered so that the generic lifecycle engine works end to end with stub agents before any real terminal agent is written. From feature 007 onward the platform can already run a use case through T0–T9 with placeholder agents, so every later feature adds capability to a working system.

| # | Feature (branch) | Delivers | Depends on | Architecture sections | Simplify if late |
| --- | --- | --- | --- | --- | --- |
| 001 | `001-platform-foundation` | Repo, uv project, Compose (Postgres, Keycloak or local auth), Alembic with the four schemas, config, CI skeleton | — | 10, 15 | Local auth instead of Keycloak |
| 002 | `002-terminal-spec-toolkit` | JSON Schema from Annex B, `adlc-spec validate` (L1–L5), `register`, registry and projection tables, shared catalogues, guardrails, metric catalogue, predicates; current T0–T9 YAMLs converted and passing | 001 | 5, Annex A | Projection tables beyond trigger, route, timeline |
| 003 | `003-lifecycle-orchestration` | Outbox, poller with dead letter, router, LangGraph terminal-run state machine (9 states), routing resolution, timers, rework / escalation counters | 001, 002 | 6 | Scheduled reminders (keep escalation) |
| 004 | `004-policy-engine` | CEL `evaluate`, `authorize`, predicate library, parameter resolution with guardrails, decision log | 002 | 5.4, 9 | — (core) |
| 005 | `005-evidence-ledger` | Ledger with hash chain, content-addressed artifact store, `run_activity`, artifact versions, use-case profile, clarification records | 001, 003 | 10 | — (core) |
| 006 | `006-agent-runtime` | Context builder, LiteLLM gateway with model catalogue and budgets, structured output and schema validator, reviewer agent, clarification requests, OpenTelemetry tracing; **stub terminal agents** | 003–005 | 7 | Langfuse (use Jaeger) |
| 007 | `007-human-inbox` | FastAPI intake / approval / clarification / waiver APIs; Streamlit intake form and inbox with sign-off, artifact table editing, escalation completion | 003, 005 | 8 | Artifact editing as comments only |
| 008 | `008-terminal-agents-t0-t2` | Real T0, T1, T2 agents, prompts, playbooks; knowledge MCP (local document folder first) | 006, 007 | 7, 13 | Single agent per terminal, no subagents |
| 009 | `009-pilot-environments` | Travel Claims golden template, synthetic claims, pilot dev / test / prod-sim containers, Locust traffic, fault injector | 001 | 14 | One injected fault (model swap) |
| 010 | `010-mcp-servers` | Git and CI, eval (DeepEval), red-team (garak / PyRIT), deploy and traffic (Docker SDK + Traefik), telemetry, ITSM mock | 006, 009 | 13 | Red-team as a fixed prompt suite |
| 011 | `011-terminal-agents-t3-t5` | T3 builder (fills the golden template), T4 evaluation with regression pack, T5 assurance with waiver path | 008, 010 | 7 | T5 mostly checklist-driven |
| 012 | `012-terminal-agents-t6-t9` | T6 readiness (mostly deterministic), T7 deployment, T8 operations with 2–3 monitors, T9 change classification, re-entry and retirement checklist | 011 | 7 | T6 / T7 deterministic with thin agent; one T8 monitor |
| 013 | `013-lifecycle-dashboard` | Journey view with reroutes, run detail, activity feed, KPI views and strip, dead-letter admin | 005, 007 | 12 | Fewer KPIs (keep reworks, escalations, time split) |
| 014 | `014-e2e-demo` | Scenario tests for D-1 to D-9, resilience tests, demo script and data reset, rehearsal fixes | all | 21 | — (must do) |

**Critical path:** 001 → 002 → 003 → 005 → 006 → 007 → 008 → 011 → 012 → 014. Features 004, 009, 010 and 013 can run in parallel with the critical path if a second developer is available.

## 7. Schedule to mid-December

The plan assumes two developers each working with a Spec Kit coding agent: one on the critical path, one on parallel features. By the end of November the whole T0–T9 lifecycle runs with stub agents and the inbox; December replaces the stubs with real agents and adds the dashboard.

&#91;embedded content: MVP build timeline · 14 features, 2 milestones\]

The demo date of 15 December is an assumption for "mid-December"; confirm it, and use the last two days as buffer for rehearsal fixes. With one developer, apply the cut-line in section 10 from feature 009 onward.

## 8. Worked example: feature 003, lifecycle orchestration

The same pattern applies to every feature: what and why at `/speckit.specify`, tech choices only at `/speckit.plan`.

> **Changed by feature 003 (ADR-01, CoE to confirm):** the terminal-run engine is a plain
> PostgreSQL state machine, not a LangGraph checkpointer. Run state lives in one row per run
> and each signal is applied in one transaction, so the run, its ledger record and its outcome
> event are written together. LangGraph remains the choice for agent graphs (feature 006). The
> step 2 text below is the original proposal; see
> `specs/003-lifecycle-orchestration/research.md` R-01.

**Step 1: `/speckit.specify`** (what and why, no stack)

```text
Build the lifecycle orchestration of the Agentic ADLC platform (solution architecture section 6).

Why: every terminal T0–T9 must run the same flow, driven only by its registered terminal spec,
so the lifecycle can change by configuration (constitution I).

User stories:
- As a business owner, when I submit a use case, a T0 run opens automatically.
- As a terminal owner, when I pass, rework (with root cause), waive or terminate a run,
  the lifecycle continues to the correct terminal per that terminal's outcome model.
- As an agent, when I lack information, I can pause my run with a clarification and resume
  when a human answers, without it counting as rework.
- As the CoE, I can see stuck events (dead letters) and re-queue them after a fix.

Rules:
- Run states: opened, blocked, building, awaiting_clarification, checking, reviewing,
  awaiting_sign_off, escalated, closed (transitions as in section 6.2).
- One active run per use case per terminal; duplicate events are ignored by event id.
- Rework beyond max_rework_cycles, SLA breach, clarification limit or agent budget → escalated.
- A closing run writes its ledger record and next event in one transaction.
- Event names follow Annex A.3; routing uses route_by_root_cause, event_routes and change classes.

Acceptance: demo moments D-2, D-3, D-4, D-7, D-9 can be driven with stub agents;
events survive an orchestrator restart; an undeliverable event is dead-lettered after 5 attempts.
```

**Step 2: `/speckit.clarify`** — expect questions such as: *Can a blocked run time out? Which role answers a clarification when the RACI has no R? Does an exception route to the next terminal immediately or after waiver approval?* Answer from the architecture, or record the decision in the spec.

**Step 3: `/speckit.plan`** (stack and constraints)

```text
Python 3.12, uv. LangGraph StateGraph for the terminal run with the Postgres checkpointer;
human waits via LangGraph interrupts resumed by the approval API.
Outbox table and poller in the events schema (FOR UPDATE SKIP LOCKED, LISTEN/NOTIFY,
retries 10s/1m/5m/15m, dead letter after 5). Router as a module behind a Router interface.
Read routing data from spec projection tables (002). Write ledger and outbox via the ledger
module (005) in one SQLAlchemy transaction. Tests with pytest and a Postgres test container.
No platform code may contain terminal-specific branching (constitution I).
```

**Steps 4–8:** `/speckit.checklist` on "routing and audit requirements"; `/speckit.tasks` produces ordered tasks (schema and migrations → outbox and poller → router → state machine → routing resolution → timers → dead-letter admin API → tests); `/speckit.analyze`; then `/speckit.implement` and `/speckit.converge` until converged; PR review and merge.

## 9. Development practices and definition of done

**Testing layers**

| Layer | What | Tooling | Runs |
| --- | --- | --- | --- |
| Spec tests | All `adlc-specs` pass validation; event graph complete | `adlc-spec validate` | Every PR touching `adlc-specs/` |
| Unit | Policy rules and predicates, parameter resolution, routing resolution, hash chain, state transitions (test-first) | pytest, hypothesis for state machines | Every PR |
| Integration | Orchestrator ↔ policy ↔ ledger ↔ outbox ↔ router; APIs; MCP servers against mocks | pytest + Postgres test container | Every PR |
| Agent quality | Each terminal agent on 2–3 small synthetic reference use cases: schema-valid output, reviewer agreement, no forbidden tool calls | DeepEval + recorded runs | Nightly and on prompt or playbook change |
| Scenario (end to end) | D-1 to D-9 with stub agents first, real agents later | pytest scenario suite driving the API | Nightly; before every demo rehearsal |
| Resilience | Orchestrator restart mid-run, duplicate events, dead letter | pytest | Nightly |

**Agent development rules**

- Prompts and playbooks are versioned files reviewed like code; each change triggers the agent quality suite.
- Agents run against recorded model responses in CI where possible, so tests are deterministic and cheap; live-model runs are nightly.
- Each lifecycle agent has a token budget and step limit from configuration from day one.

**Definition of done (per feature)**

- [ ] Spec, plan and tasks approved at gates 1–3; `/speckit.analyze` clean; `/speckit.converge` reports converged
- [ ] Tests at the layers the feature touches pass in CI; coverage of core modules ≥ 80%
- [ ] No terminal-specific or use-case-specific values in code (constitution I, II)
- [ ] Every new dependency has an OSI licence recorded in the plan
- [ ] `run_activity` rows and traces emitted for new steps
- [ ] Names follow Annex A; README for the module updated
- [ ] Demo moments the feature supports shown in the scenario suite

## 10. Risks, cut-line and changes to the solution architecture

**Risks specific to the build**

| Risk | Mitigation |
| --- | --- |
| Five weeks is tight for 14 features | Stub agents early (006) so the lifecycle demo works end to end by week 3; cut-line below; two developers on parallel features |
| Spec Kit overhead on small features | Combine very small features (e.g. 004 and 005) into one Spec Kit cycle if the gates add more time than they save |
| Coding agent drifts from architecture | Constitution articles checked at plan; `/speckit.analyze` before implement; architect reviews every plan |
| Lifecycle agent output quality | Narrow artifact schemas, strong playbooks, agent quality suite from feature 008 |
| T3 building a working pilot agent | Golden template: T3 fills a prepared pilot skeleton rather than generating from scratch |
| Self-hosting weight (Langfuse, Keycloak) | Jaeger and local auth as fallbacks, decided in feature 001 |

**Cut-line (protect the demo).** If the schedule slips, simplify in this order, keeping D-1 to D-9 demonstrable: (1) dashboard KPIs reduced to reworks, escalations, clarifications and time split; (2) T6 and T7 deterministic with a thin agent; (3) T8 with one monitor and one injected fault; (4) T5 checklist-driven with a fixed red-team prompt suite; (5) artifact editing as comments only. Never cut: orchestration states and routing, policy enforcement, ledger integrity, human sign-off.

**Changes needed in the solution architecture**

- Section 17: UI is Streamlit (not React) for the MVP; model gateway is LiteLLM; artifact store is a local content-addressed store (not MinIO); identity is Keycloak or local accounts.
- Section 5.5 and Annex A.6: terminal specs live in `adlc-specs/` because Spec Kit owns `specs/`.
- Section 20: add ADR for Spec Kit and the coding agent used with it.

## Sources

- [Spec Kit installation guide](https://github.github.com/spec-kit/installation.html) — install commands, `specify init` options, supported agents, command list
- [Spec Kit quickstart](https://github.github.com/spec-kit/quickstart.html) — command order, `/speckit.converge`, tech stack belongs in the plan step
- [Spec Kit site](https://speckit.org/)
