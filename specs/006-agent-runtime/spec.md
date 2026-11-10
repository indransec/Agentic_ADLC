# Feature Specification: Agent Runtime

**Feature Branch**: `006-agent-runtime`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Feature 006 agent-runtime (build plan §6 row 006; SA §7 agent
architecture: 7.2 runtime pattern, 7.3 registries, 7.4 guardrails; SA §6.2 run states; NFR-06
cost; ADR-02: every model call goes through a LiteLLM gateway, Anthropic primary, then OpenAI,
then Gemini): model gateway with a model catalogue and budgets, context builder, structured
output validation, the real common reviewer agent, clarifications, tool-access checks and
tracing. Terminal agents stay stubs until feature 008."

## User Scenarios & Testing *(mandatory)*

Agents build, humans decide (constitution III). This feature gives every lifecycle agent the
same runtime:

1. it receives a reproducible context pack;
2. it calls models only through one gateway that records provider, model, tokens and cost;
3. its output is checked against the spec's artifact schemas before anything else sees it;
4. it stops when it reaches its step, token or time limit.

The common reviewer becomes a real, model-based agent that judges the artifacts without seeing
how they were built. Terminal agents T0–T9 keep returning synthetic artifacts, but now through
this runtime, so feature 008 only adds prompts and playbooks.

### User Story 1 - Every model call goes through one gateway (Priority: P1)

An agent or the reviewer asks for a model by **tier**, not by name. The tier comes from the
terminal spec (`actors.agent.model_tier`: `reasoning`, `coding` or `standard`) and reflects the
task's complexity. A model catalogue maps each tier to an ordered list of models:

| Tier | Primary (Anthropic) | Fallback 1 | Fallback 2 |
| --- | --- | --- | --- |
| reasoning | Claude Opus 5.5 | OpenAI model for the tier | Gemini model for the tier |
| coding | Claude Opus 5.5 | OpenAI model for the tier | Gemini model for the tier |
| standard | Claude Sonnet 5.5 | OpenAI model for the tier | Gemini model for the tier |

When Anthropic is unavailable (an error, a rate limit or a timeout), the gateway tries OpenAI,
then Gemini. When a model refuses, or answers with output that does not fit, the gateway does
**not** move to another provider: the same model is asked again, and then the step fails. A
gate must never pass because a different model was more willing.

**Why this priority**: every other story calls models. One gateway is what makes cost,
provider changes and audit possible (ADR-02, NFR-06).

**Independent Test**: with the providers faked at the gateway, a reasoning-tier call is answered
by the primary; when the primary is made unavailable, the first fallback answers and the call
record says so; when the primary refuses, no fallback is tried.

**Acceptance Scenarios**:

1. **Given** a reasoning-tier call and all providers available, **Then** the primary answers,
   and the call is recorded with:
   - run, terminal, tier, provider and model;
   - prompt version hash;
   - tokens in and out, cost and latency;
   - `fallback = false`.
2. **Given** the primary returns a rate-limit error or times out, **Then** the first fallback
   answers and the record shows which providers were tried and why.
3. **Given** the primary refuses or returns output that does not fit, **Then** no other provider
   is tried; the same model is asked again up to the limit, and then the step fails with the
   reason.
4. **Given** a provider has no key configured, **Then** it is skipped without an error.
5. **Given** every provider in the tier's list is unavailable, **Then** the step is not counted
   as an attempt. It is retried later, and the run escalates with reason `model_unavailable`
   once the configured outage limit has passed.

---

### User Story 2 - Agents run inside a bounded, reproducible runtime (Priority: P1)

When a run reaches `building`, the runtime:

1. **Builds the context pack** (SA §7.2):
   - the pinned terminal spec, resolved for the use case;
   - the use-case profile version the run opened with (feature 005);
   - the earlier evidence named in the spec's prerequisites;
   - the trigger evidence, such as a rework comment and defect log;
   - answered clarifications;
   - the controls that failed on the previous attempt;
   - the agent's playbooks.
2. **Records the pack's hash** with the run, together with the hashes of the agent version, the
   prompt and the playbooks.
3. **Runs the agent** within its step limit, token budget and timeout.
4. **Validates the agent's output** against the column schemas in the spec's
   `evidence.artifacts`. Output that does not fit goes back to the agent, up to a limit.

A run that reaches a limit escalates (feature 003).

The ten terminal agents are still stubs: they return synthetic artifacts without calling a
model. They now run through this same runtime, so the context pack, the hashes and the
validation are exercised by every existing scenario.

**Why this priority**: the runtime is what feature 008 plugs real agents into, and reproducible,
bounded runs are a precondition for trusting their output (constitution V, VI).

**Independent Test**: a T1 run with a scripted agent records a context-pack hash. The same
inputs give the same hash. Invalid output is returned to the agent and then counted as a failed
attempt. A run that goes over its token budget escalates.

**Acceptance Scenarios**:

1. **Given** two runs with identical inputs, **Then** their context-pack hashes are equal.
   Changing any input (spec version, profile version, an answered clarification, a playbook)
   changes the hash.
2. **Given** the agent returns a table with a missing column, **Then** the agent is told what is
   wrong and asked again. When it still fails after the configured number of corrections, the
   attempt counts as a failed build attempt: the run goes back to `building` or escalates at the
   retry limit, as for a failed blocking control.
3. **Given** an agent run reaches its token budget, step limit or timeout, **Then** the run
   escalates with the limit named as the reason.
4. **Given** text from a grounding document or a tool output says "ignore your instructions",
   **Then** it reaches the model only inside a block labelled as data, never as an instruction.
5. **Given** the stub terminal agents and the stub reviewer, **Then** the 003, 004 and 005
   scenario suites pass unchanged.

---

### User Story 3 - An independent reviewer scores every run (Priority: P1)

After the controls pass, the common reviewer agent:

- scores each checklist item of the terminal (for example CHK-T1-01 "Requirements traceable to
  T0 problem");
- writes a finding where an item falls short;
- recommends an outcome.

It sees only:

- the checklist;
- the artifacts;
- the control results;
- the earlier evidence the terminal's prerequisites name.

It never sees the builder's prompt, messages or reasoning (SA §7.2 point 5), so its judgement is
independent and can be reproduced. Its recommendation is advice: people still decide (feature
003), and feature 005 records the checklist results.

**Why this priority**: the reviewer is the first real model-based judgement in the platform, and
the build plan places it here so feature 008's agents are reviewed from their first run.

**Independent Test**: a T1 run with the real reviewer and a scripted model gives a recommendation
with one score per checklist item. The reviewer's input contains none of the builder's messages.
Output that does not fit is retried and then escalates the run.

**Acceptance Scenarios**:

1. **Given** a T1 run in `reviewing`, **Then** the reviewer returns a recommendation with:
   - one score per item of the T1 checklist (scores from 0 to 3);
   - findings tied to items;
   - a recommended outcome of `pass`, `rework` or `exception`, with a reason.
2. **Given** the recommendation is `rework`, **Then** it names a root cause from the
   root-cause catalogue.
3. **Given** the reviewer's input is inspected, **Then** it contains none of the builder's
   prompt, messages or intermediate output.
4. **Given** the reviewer cannot judge an item from the evidence, **Then** it raises a
   clarification (feature 003) instead of guessing.
5. **Given** the reviewer's output does not fit after the configured corrections, **Then** the
   run escalates with reason `reviewer_failed`, and people can still complete and decide it.
6. **Given** the reviewer is set to stub in configuration (tests, or no provider keys), **Then**
   the stub reviewer is used and the run is otherwise unchanged.

---

### User Story 4 - Agents ask before guessing and act only with permission (Priority: P2)

An agent or the reviewer that lacks information raises a clarification. The clarification
states:

- the questions;
- the role it is addressed to;
- where it looked: the grounding sources and evidence it searched.

A clarification without that last part is treated as output that does not fit (SA §6.2:
"try grounding first").

Every tool or data access an agent asks for is checked first by the policy engine (feature 004),
run-scoped. A refused access is not performed, and the refusal is given back to the agent with
its reason.

**Why this priority**: these rules keep agents honest and inside their permissions
(constitution IV, XI). The real tools arrive with features 008 and 010; the checks must exist
before them.

**Independent Test**: a scripted agent asks for an allowed tool and a denied one. The first runs;
the second is refused with the policy reason and a decision is logged. A clarification without
"looked in" is returned to the agent.

**Acceptance Scenarios**:

1. **Given** a T1 agent asks to read `knowledge_base` (allowed for T1), **Then** the access is
   authorized, performed, and its output is wrapped as data.
2. **Given** a T1 agent asks to write `ledger.T0` (denied for T1), **Then** it is refused, the
   refusal reason reaches the agent, and a policy decision is logged.
3. **Given** an agent asks for a tool on behalf of another run, **Then** it is refused (run
   scope).
4. **Given** an agent raises a clarification with questions, an addressed role and the places it
   looked, **Then** the run moves to `awaiting_clarification` (feature 003).

---

### User Story 5 - Cost and traces are visible per run and use case (Priority: P2)

The CoE and terminal owners can see, from recorded data:

- what each run cost in tokens and money, per model call;
- totals per terminal and per use case;
- how often a fallback provider answered.

Every model call and agent step appears as a trace span with run, use case, terminal, tier,
provider, model, tokens and cost. Spans never contain prompt text or artifact content.

**Why this priority**: NFR-06 requires lifecycle cost per terminal. Traces are how a slow or
expensive step is found (constitution X).

**Independent Test**: after a T0–T2 walk with scripted models, the cost per run, per terminal and
per use case adds up to the sum of the recorded calls, and the trace has one span per call
without content.

**Acceptance Scenarios**:

1. **Given** a run with three model calls, **Then** its cost is the sum of the three recorded
   calls, and its terminal's and use case's totals include it.
2. **Given** a use case reaches its configured lifecycle cost alert level, **Then** an alert is
   recorded once for that level.
3. **Given** the traces of a run, **Then** each model call has a span with the attributes above,
   and no span attribute contains prompt or artifact text.

---

### Edge Cases

**Models and providers**

- A model answers in time but with an empty or truncated response: this is output that does not
  fit (same model, corrections, then the step fails), not an outage.
- A fallback model answers, and its output is later rejected by controls or people: the record
  shows the fallback, so reviewers can see which model produced the artifact.
- A model returns tokens without usage figures: the call is recorded with the usage the gateway
  could count, and marked `usage_estimated`.
- A provider's price is missing from the catalogue: cost is recorded as unknown (not zero), and
  the call is still allowed.
- The catalogue names a model whose provider has no key: that entry is skipped. If no entry of
  a tier can run, the step behaves as a full outage (US1 scenario 5).

**Runtime**

- The agent's time limit is longer than the orchestrator's lease on the step: refused when
  settings load, so a running step is never taken over by another worker.
- The worker crashes during an agent run: the step is interrupted and redone (feature 003). The
  model calls already made stay recorded and are counted in cost.
- Two attempts of the same run produce the same artifacts: feature 005 stores no new version.

**Reviewer**

- The checklist has an item the reviewer does not score: the output does not fit.
- The reviewer recommends `terminate`, or any status other than `pass`, `rework` or
  `exception`: the output does not fit (the reviewer's right is `recommend`; terminating is a
  human decision).

## Requirements *(mandatory)*

### Functional Requirements

**Model gateway**

- **FR-001**: Every model call by agents and the reviewer MUST go through one gateway. No other
  module calls a provider.
- **FR-002**: A model catalogue (shared spec catalogue, versioned with the specs) MUST map each
  model tier to an ordered list of models. Each entry has:
  - provider and model id;
  - price per input token and per output token;
  - the highest data class the model is approved for.

  Initial primaries:
  - `reasoning`: Anthropic Claude Opus 5.5;
  - `coding`: Anthropic Claude Opus 5.5;
  - `standard`: Anthropic Claude Sonnet 5.5.

  OpenAI and then Gemini follow as fallbacks per tier.
- **FR-003**: The tier for a call MUST come from the terminal spec's `actors.agent.model_tier`
  (the reviewer uses `reasoning`). There is no runtime choice of model by content.
- **FR-004**: The gateway MUST move to the next model in the list only on a provider error, a
  rate limit or a timeout. A refusal, an empty answer or output that does not fit MUST be
  retried on the same model up to a configured number of times, and then fail the step with the
  reason.
- **FR-005**: The gateway MUST skip a model:
  - whose provider has no key configured;
  - whose approved data class is below the run's data ceiling (the terminal's
    `authorities.data_access.max_class`).

  If no model of the tier can run, the step behaves as a full outage (FR-006).
- **FR-006**: When no model of the tier is available, the step MUST NOT count as an attempt. The
  run stays in its state and is retried after a back-off. It escalates with reason
  `model_unavailable` once the configured outage limit has passed.
- **FR-007**: Each model call MUST be recorded (append-only) with:
  - run, use case, terminal, agent id and version, tier;
  - provider and model;
  - the prompt version hash and the context-pack hash;
  - tokens in and out, and cost;
  - latency and outcome;
  - the providers tried before it and why;
  - `fallback` (true when a model other than the first available answered).
- **FR-008**: Provider keys MUST come from settings in the environment only, never from specs,
  the database or the repository.

**Context and registries**

- **FR-009**: The runtime MUST build a context pack for each agent attempt, containing:
  - the pinned terminal spec, resolved for the use case;
  - the profile version the run opened with;
  - the earlier evidence named in the spec's prerequisites (by ledger record and artifact
    version);
  - the trigger evidence;
  - answered clarifications;
  - the previous attempt's failed controls;
  - the agent's playbooks.
- **FR-010**: The context pack MUST have a hash over its normalised content. Identical inputs
  give the same hash. The hash, the agent version, the prompt hash and the playbook hashes MUST
  be recorded with each attempt.
- **FR-011**: A lifecycle agent registry MUST list each agent with:
  - id and version;
  - a system prompt reference;
  - model tier;
  - tool bindings.

  A prompt registry MUST hold versioned prompts. Both are folders in the repository, loaded and
  checked at registration (SA §7.3 MVP form). Each run uses the agent named in its pinned spec.
- **FR-012**: Grounding documents, tool outputs and other retrieved text MUST reach a model only
  inside blocks labelled as data. The system prompt states that such blocks are not
  instructions (SA §7.4).

**Structured output and limits**

- **FR-013**: Agent output MUST be validated against the spec's `evidence.artifacts` columns
  before it is stored or checked. A missing artifact, a missing or unknown column, or a
  non-table where a table is declared does not fit. Output that does not fit MUST be returned to
  the agent with the reasons, up to a configured number of corrections. After that, the attempt
  MUST count as a failed build attempt (the same counter and limit as failed blocking controls,
  feature 003).
- **FR-014**: Each agent run MUST have a step limit, a token budget and a timeout from
  configuration, per model tier, with optional overrides per terminal. Reaching any of them MUST
  end the attempt with `BudgetExceeded` naming the limit, so the run escalates (feature 003).
- **FR-015**: The agent timeout MUST be shorter than the orchestrator's step lease. Settings that
  break this MUST be refused at start-up.

**Reviewer**

- **FR-016**: The common reviewer MUST be a model-based agent on the `reasoning` tier. It MUST
  receive only:
  - the terminal's checklist items;
  - the artifacts;
  - the control results;
  - the earlier evidence the prerequisites name;
  - answered reviewer clarifications.

  It MUST NOT receive any builder prompt, message or intermediate output.
- **FR-017**: The reviewer's output MUST give:
  - a score from 0 to 3 for every checklist item;
  - findings tied to items, or general findings;
  - a recommended outcome allowed for the reviewer (`pass`, `rework` or `exception`), with a
    reason;
  - a root cause from the root-cause catalogue when the outcome is `rework`.

  Output that does not fit MUST be corrected as in FR-013. After the last correction, the run
  MUST escalate with reason `reviewer_failed`.
- **FR-018**: A configuration switch MUST select the stub reviewer instead (for tests, and for
  runs without provider keys). The ledger and trace MUST show which reviewer was used.

**Clarifications and tool access**

- **FR-019**: A clarification from an agent or the reviewer MUST state its questions, its
  addressed role (or none, so feature 003's default role applies) and where it looked. One
  without the places it looked does not fit (FR-013).
- **FR-020**: Every tool or data access an agent asks for MUST first pass the policy engine's
  run-scoped authorize (feature 004). A refused access MUST NOT be performed. The refusal and
  its reason are given back to the agent.

**Cost and tracing**

- **FR-021**: Cost MUST be computed per call from the catalogue prices and recorded. Totals per
  run, terminal and use case MUST be readable (for features 007 and 013). A call with an unknown
  price has cost "unknown", not zero.
- **FR-022**: A lifecycle cost alert level per use case MUST be configurable. When a use case's
  total first reaches a level, one alert is recorded. Alerts do not stop runs; budgets per agent
  run (FR-014) do.
- **FR-023**: Every model call and agent step MUST be traced as a span with:
  - run, use case, terminal, agent, tier;
  - provider and model;
  - tokens and cost;
  - outcome and fallback.

  Span attributes MUST NOT contain prompt text, model output or artifact content.

**Stubs and compatibility**

- **FR-024**: The stub terminal agents MUST run through the runtime: context pack, hashes,
  validation and limits apply, but no model is called.
- **FR-025**: The feature 003 interfaces (`AgentRunner`, `Reviewer`, `BuildContext`,
  `ReviewContext`) MUST stay the boundary between the orchestrator and the runtime. Additions are
  optional fields only.
- **FR-026**: No terminal-specific values or branching (constitution I): tiers, artifacts,
  checklists, permissions and data ceilings come from the specs and catalogues.

### Key Entities

- **Model catalogue entry**: tier, order, provider, model id, prices, approved data class.
- **Model call record**: one model request with:
  - run, agent and tier;
  - provider, model, the providers tried and fallback;
  - tokens, cost, latency and outcome;
  - prompt hash and context-pack hash.
- **Agent attempt record**: per build or review attempt, with:
  - agent id and version;
  - prompt hash, playbook hashes and context-pack hash;
  - corrections used;
  - result (artifacts, clarification, budget exceeded, failed) and the limit reached.
- **Lifecycle agent**: registry entry with id, version, prompt reference, tier and tool bindings.
- **Prompt**: versioned text with a hash.
- **Cost alert**: use case, level, total reached, time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of model calls in a full T0–T8 walk with scripted models have a call record
  with provider, model, tokens and cost (or cost marked unknown), and none bypass the gateway.
- **SC-002**: For an outage of the primary, 100% of calls are answered by the first available
  fallback and recorded as such. For a refusal, 0% fall back.
- **SC-003**: The same inputs give the same context-pack hash in 100% of repeated runs. Changing
  any one input changes it.
- **SC-004**: Output that does not fit never reaches controls, the ledger or people. 100% of such
  outputs are either corrected or end as a failed attempt.
- **SC-005**: Every token-budget, step-limit or timeout breach escalates its run, with the limit
  named, within one orchestrator round.
- **SC-006**: The reviewer's input contains no builder prompt, message or intermediate output in
  100% of reviews. Every recommendation scores every checklist item.
- **SC-007**: Cost per run, terminal and use case equals the sum of its recorded calls (to the
  cent).
- **SC-008**: The 003, 004 and 005 scenario suites pass with stub terminal agents running through
  the runtime. Tests make no network calls.
- **SC-009**: The runtime's own overhead (context pack, validation, recording) adds less than
  200 ms per agent attempt, excluding model time.

## Assumptions

- **Models and data:**
  - Real terminal agents (T0–T2) come in feature 008. Knowledge sources and tool servers (MCP)
    come in features 008 and 010. This feature provides the tool-access check and the data
    wrapping they use, tested with a fake tool.
  - The exact OpenAI and Gemini model ids per tier, and all prices, are configuration values in
    the model catalogue, set during planning and confirmed by the CoE.
  - All three providers are assumed approved up to `confidential_masked`, the highest ceiling
    any terminal spec uses today. MVP data is synthetic. The CoE confirms provider approvals per
    data class before real data is used.
- **Budgets:**
  - The use-case profile's `token_budget` (emitted at T2) is the **pilot agent's** budget, not
    the lifecycle agents'. Lifecycle agent budgets come from configuration (FR-014), and the
    lifecycle cost alert per use case from FR-022.
- **Tests and demo:**
  - Tests use a fake gateway that returns scripted answers. The demo stack without provider keys
    uses the stub reviewer.
- **Out of scope:**
  - Prompt and model evaluation of the lifecycle agents themselves (SA §7.4, replaying reference
    use cases) is out of scope; it is planned with feature 008.
  - Streaming of model output to users is out of scope.
