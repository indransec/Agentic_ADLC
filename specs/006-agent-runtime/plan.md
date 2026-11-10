# Implementation Plan: Agent Runtime

**Branch**: `006-agent-runtime` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-agent-runtime/spec.md`

## Summary

A new package, `src/adlc/agents/`, gives every lifecycle agent and the common reviewer one
runtime behind feature 003's `AgentRunner` and `Reviewer` interfaces:

- **Model gateway**: on LiteLLM for Anthropic, OpenAI and Gemini (ADR-02, decided 2026-11-10). A
  model catalogue per tier sets the order: Anthropic, then OpenAI, then Gemini. The gateway falls
  back only on outages, never on refusals. Every call is recorded with provider, model, tokens,
  cost and fallback.
- **Context pack**: built from the pinned spec, profile version, prerequisite evidence, trigger,
  clarifications, failed controls and playbooks. It is hashed, and retrieved text goes into data
  blocks.
- **Registries**: an agents catalogue, the model catalogue, and versioned prompts. They are
  validated and registered by the feature 002 toolkit.
- **Limits and validation**: structured output is checked against the spec's artifact columns,
  with corrections. Step, token and time limits per tier escalate a run when reached.
- **Reviewer**: a real reviewer on the reasoning tier, with independent input. It scores every
  checklist item and recommends `pass`, `rework` or `exception`.
- **Tool gate**: every agent tool call passes feature 004's `authorize`.
- **Cost**: views per run, terminal and use case, and alert levels per use case.
- **Feature 003 additions**: `failed` and `model_unavailable` results, deferral of runs during
  an outage, and two escalation triggers.

Terminal agents stay stubs, now running through the runtime. `ADLC_REVIEWER_MODE=stub` keeps the
stub reviewer for tests and keyless runs.

## Technical Context

**Language/Version**: Python 3.12 (existing `adlc` package, uv, mypy strict, ruff)

**Primary Dependencies**:

- **Already used:** SQLAlchemy 2, psycopg 3, jsonschema, ruamel.yaml, OpenTelemetry, cel-python
  (004).
- **New:**
  - `litellm==1.106.5` (MIT core; released 2026-10-27);
  - `respx` (BSD-3, development only) for LiteLLM HTTP contract tests.

**Storage**: PostgreSQL. Migration `0006` adds:

- `spec.prompt_registry`;
- `run.agent_attempt`, `run.model_call` and `run.cost_alert`;
- `run.terminal_run.model_unavailable_since`;
- two escalation triggers;
- three cost views.

**Testing**: pytest.

- **Unit:** gateway rules (with a fake transport), outcome classification, catalogue resolution,
  context pack and hash, output validation, reviewer schema, limits, state-machine additions
  with hypothesis.
- **Contract:** the `litellm_contract` marker, using respx to check LiteLLM request bodies and
  response mapping for the three providers.
- **Integration:** runtime in the orchestrator with `FakeGateway`, deferral and escalation,
  records and cost views, tool gate with feature 004.
- **Scenarios:** the 003, 004 and 005 suites with stub agents through the runtime.

**Target Platform**: library in the orchestrator process (the worker runs agent steps). There is
no new service.

**Project Type**: library inside the platform package.

**Performance Goals**: runtime overhead under 200 ms per attempt, excluding model time (SC-009).

**Constraints**:

- **Fallback:** only on outages (FR-004).
- **Keys:** provider keys only in the environment (FR-008).
- **Spans:** no prompt or artifact text in spans (FR-023).
- **Timeouts:** each agent timeout, plus a 30 s margin, must be shorter than the worker lease
  (FR-015).
- **Tests:** no network in tests.
- **Specs:** no terminal-specific code (constitution I).

**Scale/Scope**: 10 terminals plus the reviewer; a few model calls per attempt; tens of runs per
use case.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| litellm 1.106.5 | One client for Anthropic, OpenAI and Gemini; no proxy, router or callbacks | MIT (core; the `enterprise/` folder is not used) |
| respx (dev) | Mock HTTP for the LiteLLM contract tests | BSD-3-Clause |

LiteLLM brings transitive dependencies (openai, tiktoken, tokenizers, huggingface-hub, aiohttp,
jinja2, boto3), which make the orchestrator image larger. They are recorded in `uv.lock` and
scanned like the others.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Tiers, agents, prompts, artifacts, checklists, data ceilings and permissions come from specs and catalogues; the scan covers `agents/` | Pass |
| II Superset, not values | Model choices and prices live in the catalogue; limits in settings | Pass |
| III Agents build, humans decide | The reviewer only recommends; agents cannot set statuses; `terminate` is never a reviewer output | Pass |
| IV Separation of duties | The reviewer's input never contains builder reasoning; every tool call is authorized run-scoped | Pass |
| V Evidence-first | Context-pack, prompt and playbook hashes and every model call are recorded append-only | Pass |
| VI Deterministic first | Output validation, limits, fallback rules and controls are deterministic code; the model only proposes | Pass |
| VII Interfaces | `ModelGateway` (LiteLLM and fake), `AgentRunner` and `Reviewer` (003), `ToolGate`; providers swap by catalogue | Pass |
| VIII Open source | LiteLLM (MIT), respx (BSD-3) | Pass |
| IX Test first | Gateway rules, validation, context hash, reviewer schema and state-machine additions are written test-first | Pass |
| X Observable | Spans per model call and agent step, with cost and fallback; records queryable | Pass |
| XI Secure | Keys from the environment only; data-class gate per model; retrieved text wrapped as data; no prompt text in traces | Pass |
| XII Simplicity | No LangGraph, no LiteLLM proxy or router; one synchronous loop | Pass |
| XIII Naming | Tables, columns, ids and spans follow Annex A | Pass |

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/006-agent-runtime/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── gateway.md                    # ModelGateway, outcomes, fallback rules, records
│   ├── runtime.md                    # build and review attempts, engine duties, tool gate
│   ├── reviewer.md                   # reviewer and builder output schemas and validation
│   └── state-machine-additions.md    # feature 003 rows, deferral, properties
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/adlc/agents/
├── __init__.py  README.md
├── catalogue.py     # model catalogue and agents catalogue from the registry; tier resolution
├── gateway.py       # ModelGateway protocol, LiteLLMGateway, outcome classification, records
├── fake.py          # FakeGateway (tests and local scripting)
├── prompts.py       # prompt registry access (id, version, hash, text)
├── context.py       # context pack: sections, normalised hash, message rendering, data blocks
├── output.py        # builder and reviewer output schemas, parsing, correction messages
├── limits.py        # per-tier limits, terminal overrides, attempt budget tracking
├── runner.py        # RuntimeAgentRunner (stub and model implementations), attempt records
├── reviewer.py      # RuntimeReviewer, mapping to Recommendation
├── tools.py         # ToolGate, ToolOutput/ToolRefused, FakeTool
├── cost.py          # cost per call, alerts, cost views
└── store.py         # SQL for agent_attempt, model_call, cost_alert
adlc-specs/shared/model_catalogue.yaml  adlc-specs/shared/agents.yaml
adlc-specs/schema/catalogues/{model_catalogue,agents}.schema.json
adlc-specs/schema/prompt-front-matter.schema.json
adlc-specs/prompts/common-terminal-reviewer.md   # reviewer system prompt (v1.0.0)
src/adlc/spec_toolkit/{loader,register,rules/cross_spec}.py  # prompts, two catalogues, new rules
db/migrations/versions/0006_agent_runtime.py
src/adlc/orchestration/interfaces.py  # AttemptFailed, ModelUnavailable, Recommendation fields
src/adlc/orchestration/states.py      # failed and model_unavailable results
src/adlc/orchestration/engine.py      # release connection before agent call; deferral; signals
src/adlc/orchestration/worker.py      # build_orchestrator wires the runtime
src/adlc/config/settings.py           # keys, limits, corrections, outage limit, alerts, reviewer mode
docs/build-plan.md, docs/solution-architecture.md  # ADR-02
tests/unit/agents/  tests/integration/agents/
```

**Structure Decision**: an `agents/` layer beside `orchestration/`, `policy/` and `ledger/`. The
orchestrator depends only on its own interfaces, and `build_orchestrator` injects the runtime.

## Complexity Tracking

No constitution violations; nothing to justify.
