# Research: Agent Runtime

Decisions for feature 006, each with its rationale and the alternatives considered.

## R-01 Model gateway: LiteLLM for all three providers

**Decision**:
- **One gateway:** `adlc.agents.gateway.LiteLLMGateway` is the only module that calls a provider
  (FR-001). It calls `litellm.completion` once per model attempt, with `num_retries=0`. The gateway
  owns the provider order, the retries on the same model and the call records. LiteLLM's `Router`,
  its fallbacks and its callbacks are not used.
- **Version:** `litellm==1.106.5`, pinned exactly. It was released on 2026-10-27, so it is at least
  two weeks old. Its price map already lists `claude-opus-5-5` ($4 / $20 per million tokens) and
  `claude-sonnet-5-5` ($2 / $10).
- **Calls:** synchronous, because the orchestrator worker is synchronous.
- **Import settings:** the gateway sets `LITELLM_LOCAL_MODEL_COST_MAP=True`, so the import makes no
  network call. It also turns off LiteLLM's telemetry and success and failure callbacks.
- **Keys:** keys are passed per call (`api_key=`) from `ADLC_*` settings. They are never put into
  the process environment.
- **Request settings:** each request sends only `model`, `messages`, `max_tokens`, `timeout`, and
  the catalogue entry's `params` (empty by default). The gateway never sends:
  - `temperature`, `top_p` or `top_k` (Claude Opus 5.5 and Sonnet 5.5 reject sampling settings);
  - a `thinking` budget (thinking is always on for Opus 5.5);
  - `reasoning_effort`;
  - `response_format` (see R-02);
  - forced `tool_choice`.

  A contract test checks the outgoing request body for each provider.
- **Anthropic refusal fallback:** Anthropic's server-side refusal fallback is **not** enabled,
  because refusals must never fall back to another model (FR-004).

**Rationale**: this is the user's decision of 2026-11-10 (ADR-02: LiteLLM for all three). The
gateway keeps routing and recording in our code, so a change of LiteLLM version or provider does
not change the rules.

**Alternatives**:
- The official Anthropic SDK for Claude with LiteLLM for the fallbacks. This gives exact
  refusal, usage and structured-output handling. The user declined it.
- The LiteLLM proxy. Not needed for the MVP, and it adds a service.
- The LiteLLM `Router` with fallbacks. Its fallback rules would also fire on content policy
  errors, which our rule forbids.

## R-02 Classifying outcomes: outage, refusal or failure

**Decision**: the gateway maps each LiteLLM result to one outcome:

| Outcome | LiteLLM signal | Gateway action |
| --- | --- | --- |
| `ok` | A response with text, `finish_reason` `stop` or `end_turn` | Return it |
| `outage` | `RateLimitError`, `Timeout`, `APIConnectionError`, `ServiceUnavailableError`, `InternalServerError`, `BadGatewayError`, `AuthenticationError`, `PermissionDeniedError` | Try the next model in the tier |
| `refusal` | `ContentPolicyViolationError`; `finish_reason` `content_filter` or `refusal`; an Anthropic `stop_reason` `refusal` in the provider-specific fields | Retry the same model (corrections); never fall back |
| `truncated` | `finish_reason` `length`, or empty text | Same as `refusal`: retry the same model |
| `request_error` | `BadRequestError`, `NotFoundError`, `UnprocessableEntityError` | Fail the step; never fall back. The request is ours to fix. |

An authentication or permission error moves to the next model because that entry cannot run, as
for a missing key (FR-005). It is recorded with the reason `auth`, so a wrong key shows up in the
records.

**Rationale**: fallback only for availability (FR-004).

**Alternative**: falling back on any error. Rejected by the spec.

## R-03 Structured output: JSON text checked by our validator

**Decision**:
- The agent prompt asks for one JSON object. The runtime parses the answer, from a fenced or a
  bare JSON block, and validates it against a JSON Schema built from the spec's
  `evidence.artifacts`:
  - an object per artifact;
  - a table is an array of objects whose keys are exactly the declared columns;
  - extra artifacts are refused.
- Output that does not fit is answered with a correction message listing the problems, up to
  `ADLC_AGENT_CORRECTIONS` (default 2).
- No provider feature for structured output is used through LiteLLM in the MVP.

**Rationale**:
- For Anthropic, LiteLLM implements `response_format` JSON mode with a forced tool choice. Claude
  Opus 5.5 and Sonnet 5.5 reject forced tool choice with a 400 error.
- Our own validation is needed anyway (FR-013). It behaves the same for all three providers.

**Alternatives**:
- `response_format` with a JSON schema. Rejected: Anthropic would get a 400, and the providers
  behave differently.
- Calling the Anthropic SDK's structured outputs directly. Not available, because LiteLLM is used
  for all providers (R-01).

## R-04 Registries: catalogues and a prompt folder in `adlc-specs/`

**Decision**:
- **Model catalogue:** `adlc-specs/shared/model_catalogue.yaml`, a new required catalogue with a
  schema. Each tier lists ordered entries with:
  - `provider` and `model` (the LiteLLM id, for example `anthropic/claude-opus-5-5`);
  - `input_per_mtok` and `output_per_mtok` (USD);
  - `max_data_class`;
  - optional `params`.
- **Agent registry:** `adlc-specs/shared/agents.yaml`, a new required catalogue. Each agent has
  `id`, `version`, `prompt` (`{id, version}`), `model_tier`, `tools` (permission patterns) and
  `implementation` (`stub` or `model`). The common reviewer is an entry too.
- **Prompts:** `adlc-specs/prompts/*.md`, with YAML front matter (`id`, `version`, `agent`,
  `status`). They are registered in a new `spec.prompt_registry` table, with a hash, exactly as
  playbooks are.
- **New spec-toolkit rules (feature 002):**
  - every `actors.agent.id` and `actors.reviewer` exists in `agents`;
  - an agent's `model_tier` equals the spec's `actors.agent.model_tier`;
  - every tier has at least one catalogue entry;
  - every prompt reference resolves;
  - every `max_data_class` is a known data class.

**Rationale**:
- This is SA §7.3's MVP form ("folder in repo + table").
- It reuses the 002 loader, schemas, versioning rule (L5) and registration, so a prompt change
  needs a version bump and is hashed.
- `implementation: stub` lets feature 008 switch T0–T2 to model agents by editing the catalogue
  (FR-024).

**Alternatives**:
- A separate `agents/` top-level folder. It would bypass validation and versioning.
- Prompts stored in the database only. That loses review by pull request.

## R-05 Initial catalogue values

**Decision**:

| Tier | 1 | 2 | 3 |
| --- | --- | --- | --- |
| reasoning | `anthropic/claude-opus-5-5` ($4 / $20) | `openai/gpt-6.1-sol` ($2 / $10) | `gemini/gemini-4-argon` ($2 / $10) |
| coding | `anthropic/claude-opus-5-5` ($4 / $20) | `openai/gpt-6.1-sol` ($2 / $10) | `gemini/gemini-4-argon` ($2 / $10) |
| standard | `anthropic/claude-sonnet-5-5` ($2 / $10) | `openai/gpt-6-sol` ($2 / $10) | `gemini/gemini-3.8-flash` ($0.75 / $3.75) |

- Every entry has `max_data_class: confidential_masked` (clarification of 2026-11-10).
- The Anthropic ids and prices come from Anthropic's current model table.
- The OpenAI and Gemini ids and prices come from the LiteLLM 1.106.5 price map. They are
  **proposals for the CoE to confirm**, including that each model is generally available.

**Rationale**: values live in the catalogue, not in code, so they change through a spec pull
request.

## R-05a Catalogue profiles: GPT-4o mini first in dev

**Decision** (user, 2026-11-10):
- **Profiles:** the model catalogue holds `profiles: {default: {tiers}, dev: {tiers}}`.
  `ADLC_MODEL_PROFILE` selects one (default `default`); `.env.example` sets `dev`.
- **The `dev` profile:** every tier, the reviewer's included, starts with:
  1. `openai/gpt-4o-mini`: $0.15 / $0.60 per million tokens, 128K context, 16,384 output
     tokens;
  2. `gemini/gemini-2.5-flash`: $0.30 / $2.50, 1M context, 65,536 output tokens;
  3. the `default` entries of that tier.

  The figures come from the LiteLLM 1.106.5 price map.
- **Dev keys:** `ADLC_OPENAI_API_KEY` is set. Entries without a key are skipped (`skipped` rows
  with reason `no_key`). GPT-4o mini answers as the first entry (`fallback = false`).
- **Output and context limits:** catalogue entries carry `max_output_tokens` and
  `context_tokens`. The gateway caps each call's `max_tokens` at the entry's output limit. A
  context pack larger than the entry's context window is not sent to that entry: it is
  `skipped` with reason `context`.
- **Retirement:** OpenAI retires the dated `gpt-4o-mini` snapshot on 2027-01-14 (price map). The
  dev profile must move to another small model before then.
- **Validation rules:** every profile must cover every tier, and `default` must exist.

**Rationale**:
- Cheap real-model testing in development without changing the reviewed production order. This
  was the user's choice, revised the same day from Gemini 2.5 Flash to GPT-4o mini.
- The profiles stay in the reviewed catalogue, not in settings (constitution II).

**Alternative**: a setting that reorders providers. It hides the actual order outside the specs.

## R-06 Context pack

**Decision**:
- The pack is one JSON document with ordered sections:
  1. agent (id, version, prompt hash);
  2. spec (pinned version and content hash, plus the resolved artifacts, controls and checklist);
  3. profile (version and values);
  4. evidence (prerequisite ledger records: key, record hash, artifact versions and their stored
     content);
  5. trigger;
  6. clarifications;
  7. failed controls;
  8. playbooks (id, version, hash, text).
- The pack hash is `sha256` over the pack normalised with feature 002's `normalise` (sorted keys,
  no timestamps).
- **Rendering into messages:**
  - The system prompt (from the registry) comes first and is the same for every run of an
    agent.
  - Then the spec and playbooks, which stay the same within a terminal.
  - Then the volatile sections. This order keeps provider prompt caching possible.
- **Data blocks:** every retrieved text, document or tool output is rendered as
  `<data source="…" id="…">…</data>`. A `</data` inside the text is escaped. The system prompt
  states that data blocks are never instructions (FR-012).

**Rationale**: FR-009 and FR-010, and SA §7.4.

## R-07 Limits and the worker lease

**Decision**:
- **Limits per agent attempt:**
  - `steps`: the number of model calls, counting corrections and tool rounds;
  - `tokens`: input plus output tokens;
  - `timeout`: wall-clock seconds.
- **Settings:** `ADLC_AGENT_LIMITS`, a JSON map per tier (`reasoning`, `coding`, `standard`), and
  `ADLC_AGENT_LIMIT_OVERRIDES`, a map per terminal.
- **Defaults:**

  | Tier | Steps | Tokens | Timeout |
  | --- | --- | --- | --- |
  | reasoning and coding | 8 | 400,000 | 240 s |
  | standard | 6 | 200,000 | 120 s |
- **Checks during an attempt:** the limits are checked before each call. Each call's timeout is
  the remaining time. Reaching a limit returns `BudgetExceeded("tokens" | "steps" | "timeout")`.
- **Lease rule:** settings refuse to load unless every timeout plus a 30 s margin is shorter
  than `ADLC_LEASE` (default 5 min) (FR-015).
- **Engine change:** the engine reads what the agent needs, then releases its database
  connection before calling the agent. A model call never holds a connection open in a
  transaction.

## R-08 Outage deferral, failed attempts, reviewer failure (feature 003 additions)

**Decision**:
- **New result types (feature 003 interfaces):**
  - `AttemptFailed(reason)`: output still unfit after the corrections, a refusal, or a request
    error;
  - `ModelUnavailable(detail)`: no model of the tier could run.

  Both join `AgentResult` and `ReviewResult`. They are added union members, so existing code is
  unaffected.
- **Deferral is handled by the engine, with no transition:**
  - The engine records a `deferred` activity and sets the run's `lease_until` to now plus a
    back-off: 30 s doubling, at most 5 minutes.
  - The first deferral of an outage is recorded in a new column,
    `run.terminal_run.model_unavailable_since`. Any other step result clears it.
  - When `now - model_unavailable_since` reaches `ADLC_MODEL_OUTAGE_LIMIT` (default 30 minutes),
    the engine sends the result as a signal instead.
- **State machine additions** (contract and property tests):

  | State | Signal | Result | Next state | Effects |
  | --- | --- | --- | --- | --- |
  | building | `agent_result` | `failed` | building, or escalated at the retry limit | `IncrementAutoRetry`, or `Escalate(retry_limit)`. The same counter as failed blocking controls. |
  | building | `agent_result` | `model_unavailable` | escalated | `Escalate(model_unavailable)` |
  | reviewing | `review_result` | `failed` | escalated | `Escalate(reviewer_failed)` |
  | reviewing | `review_result` | `model_unavailable` | escalated | `Escalate(model_unavailable)` |
- **Migration 0006:** the escalation-trigger check gains `model_unavailable` and
  `reviewer_failed`.

**Rationale**: an outage is not the agent's fault, so it must not use up retries (FR-006). The
state machine stays pure, and the time comparison happens in the engine.

## R-09 Reviewer

**Decision**:
- The reviewer is an agent with `implementation: model` on the `reasoning` tier. Its input is
  built only from `ReviewContext` plus the prerequisite evidence (FR-016). A test records the
  gateway requests and checks that none of the builder's prompt or messages appears.
- **Output schema:**
  - `scores`: `{item_id: 0..3}`, covering every item and nothing else;
  - `findings`: a list of `{item: id | null, text}`;
  - `recommendation`: `{status: pass | rework | exception, reason, root_cause?}`, where
    `root_cause` is required for `rework` and must be in the catalogue.

  Instead of all three, the reviewer may return `clarification: {questions, addressed_role?,
  looked_in}`.
- **Mapping to feature 003's `Recommendation`:**
  - status and scores carry over;
  - findings become `"item: text"` strings, as feature 005 parses them;
  - the new optional fields `reason` and `root_cause` are added.
- **Setting `ADLC_REVIEWER_MODE`:** `stub` (default: no spend, no keys needed) or `model`. The
  recommendation records `reviewer: stub | model` (FR-018).

## R-10 Tool gate

**Decision**:
- `ToolGate.call(run, tool, action, resource, arguments)` first calls feature 004's
  `authorize(f"agent:{run_id}", action, resource, EvalContext(...))`.
  - When refused, it returns a `ToolRefused(reason)` result to the agent loop, and the call is
    not made.
  - When allowed, it calls the tool and wraps the output as a data block.
- In 006, tools are registered in the process. Only a `FakeTool` exists, for tests. Real MCP
  tools come with features 008 and 010.

**Rationale**: FR-020 and constitution IV. The policy engine already logs every decision.

## R-11 Records, cost and alerts

**Decision**:
- **Tables:** `run.model_call`, `run.agent_attempt` and `run.cost_alert`, all append-only.
  - They are written in their own short transactions, as feature 004's policy decisions are, so
    an interrupted or rolled-back step keeps its records (spec edge case).
  - `run.agent_attempt` gets one row per build or review attempt.
- **Cost:** `cost_usd numeric(14,6)` is null when the price is unknown, and `cost_known` is false
  then.
- **Views:** `run.v_run_cost`, `run.v_terminal_cost` and `run.v_usecase_cost`. The terminal
  view is per use case and terminal, and each view gives totals, unknown counts and fallback
  counts.
- **Cost alerts:**
  - Levels come from `ADLC_COST_ALERT_LEVELS` in USD per use case (default `5,20,50`).
  - After each recorded call, the gateway inserts a `cost_alert` for every level the use case
    total has newly reached.
  - A unique `(usecase_id, level)` key makes the insert idempotent.

## R-12 Tracing

**Decision**: the spans are `adlc.model.call`, `adlc.agent.build` and `adlc.agent.review`, built
with the existing `tracing.span` helper. Inside the engine's `adlc.agent.build` span, the runtime
adds `adlc.agent.attempt`, which carries the attempt's outcome, steps, tokens and limit reached
(added during implementation; convergence T044). Their attributes are:

- ids: run, use case, terminal, agent, attempt;
- `tier`, `provider`, `model`;
- `tokens_in`, `tokens_out`, `cost_usd`;
- `outcome`, `fallback`.

A test fails if any attribute value is longer than 200 characters or contains prompt or artifact
text (FR-023). LiteLLM's own OpenTelemetry callbacks stay off.

## R-13 Tests make no network calls

**Decision**:
- **Fake gateway:** `FakeGateway`, with scripted outcomes per tier and model: text, outage,
  refusal, truncated or usage. Runtime and reviewer tests use it.
- **LiteLLM mapping tests:** the `LiteLLMGateway` mapping is tested with `respx` (BSD-3, a new
  development dependency). It intercepts the HTTP requests of the three providers. The tests
  check the outgoing bodies (no sampling settings, no thinking budget) and map recorded
  response shapes: success with usage, refusal, rate limit, timeout.
- **Network guard:** an autouse fixture replaces `litellm.completion` with a function that fails
  the test, except in tests marked `litellm_contract`. Those tests run with `respx` and allow no
  real host.

## R-14 No LangGraph in 006

**Decision**: the agent loop is a bounded loop in our code: build the pack, call the model,
validate, correct, run gated tools. LangGraph is not added in 006.

**Rationale**: constitution XII. There are no subagents yet; T3's subagents come later. The build
plan's mention of "LangGraph for agent graphs (006)" moves to the feature that introduces
subagents. The build plan row is updated with ADR-02.

## R-16 Gate 2 defaults (approved 2026-11-10)

- **Start-up:** model agents or the model reviewer with no keyed entry for a needed tier are
  refused at start-up (FR-018).
- **Data classes:** compared by rank. An unresolvable ceiling counts as the highest rank. If
  every entry is skipped for its data class or context window, the attempt fails rather than
  defers (FR-005).
- **People's text:** clarification answers, rework comments and edits are data blocks (FR-012).
- **Evidence:** prerequisite evidence carries the content of the referenced artifact versions. A
  pack larger than the token budget gives `BudgetExceeded("tokens")` (FR-009, FR-014).
- **Corrections:** each correction counts as a step (FR-014).
- **Outage start:** stored on the run (`model_unavailable_since`), so it survives restarts
  (FR-006).
- **Reviewer:** the reason and root cause are stored with the recommendation (FR-017).
- **Tools:** tool bindings declare `action:resource` (FR-020).
- **Cost:** failed calls cost zero unless usage was reported. Calls with unknown prices are
  counted separately (FR-021).
- **Spans:** attributes come from an allow list, each value at most 200 characters (FR-023).
- **Never-sent settings:** promoted from the contract to FR-004.
- **Synthetic data:** the synthetic artifacts match their declared columns exactly (checked: 0
  differences), so stub agents pass the strict rule.
- **Unconfirmed models:** a fallback model the CoE does not confirm is removed; every tier keeps
  at least one model (FR-002).

## R-15 ADR-02 in the documents

**Decision**:
- `docs/build-plan.md`, Models row: "ADR-02 (2026-11-10): commercial models through LiteLLM;
  catalogue per tier: Anthropic primary, then OpenAI, then Gemini; fallback only on availability
  errors."
- SA §17: ADR-02 is recorded as decided, with the CoE to confirm the fallback model ids and the
  data-class approvals.

## R-17 LiteLLM 1.106.5 behaviour observed (mocked HTTP probe, 2026-11-10)

- **Anthropic stop reasons:** `refusal` arrives as `finish_reason="content_filter"`, with the
  text still present. `max_tokens` arrives as `length`.
- **Anthropic request body:** keys `model`, `messages`, `system`, `max_tokens` only (no sampling
  settings). The key goes in the `x-api-key` header.
- **Anthropic reply without `usage`:** raises `APIConnectionError` (a `KeyError` inside
  LiteLLM). The gateway must not treat this as an outage: it is a malformed reply, so classify
  it as `request_error`, or catch it before the generic connection rule.
- **Errors:** 429 gives `RateLimitError`, 400 gives `BadRequestError`, a read timeout gives
  `Timeout`.
- **OpenAI:** body keys `model`, `messages`, `max_tokens`. `content_filter` and `length` pass
  through. Key in the `Authorization` header.
- **Gemini:** `SAFETY` becomes `content_filter` with content `None`; `MAX_TOKENS` becomes
  `length`. The body is `contents` plus `generationConfig.max_output_tokens`. The key is not in
  the URL.
- **Process environment:** LiteLLM did not add provider keys to the process environment.

## R-18 Data-class resolvers (user, 2026-11-11)

**Decision**:
- **Source.** A resolver in `data_classes.yaml` may name a `source` artifact column (catalogue
  1.1.0). `per_T2_prod_design` takes `T2.data_strategy.classification`.
- **Resolution.** At run time the ceiling is the highest-ranked class in that column of the use
  case's latest record of the terminal.
- **Fail closed.** If the record is missing, the column is empty, or any value is not a known
  class, the resolver stays unresolved and fails closed, as in R-16.
- **Validation.** Rule V-31 checks that the source is a declared artifact column.

**Rationale**: without it, a model review of T7 (ceiling `per_T2_prod_design`) could never run.
The code stays generic, because the terminal, artifact and column come from the catalogue.
