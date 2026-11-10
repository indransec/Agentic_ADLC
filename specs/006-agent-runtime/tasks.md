# Tasks: Agent Runtime

**Input**: Design documents from `specs/006-agent-runtime/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Constitution IX makes these test-first:

- gateway outcome classification and fallback rules;
- catalogue and profile resolution;
- output validation and corrections;
- the context-pack hash;
- limits;
- the reviewer output mapping;
- the feature 003 state-machine additions, with hypothesis.

Test tasks come first in each phase and must fail before their implementation.

**Organization**: phases follow the spec's user stories in priority order (US1–US3 P1, US4–US5
P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US5)

## Conventions used by every task

- **Where things live:** code in `src/adlc/agents/`, unit tests in `tests/unit/agents/`,
  database tests in `tests/integration/agents/` (shared `h` and `orch_template` fixtures).
- **No network:** tests never call a provider. `FakeGateway` scripts the models. Only tests
  marked `litellm_contract` reach LiteLLM, and they use `respx` to intercept its HTTP.
- **Constitution I:** no terminal ids, artifact ids, role names, model ids or provider names in
  `src/adlc/agents/`. They come from the specs and catalogues.
- **Spans and records:** spans and records never hold prompt text, model output or artifact
  content (FR-023).

---

## Phase 1: Setup

- [X] T001 Add `litellm==1.106.5` (exact pin) to the dependencies and `respx` to the dev dependencies in `pyproject.toml`, refresh `uv.lock`, and record both (MIT, BSD-3) in the plan's licence table. Register the pytest marker `litellm_contract` in `pyproject.toml`.
- [X] T002 Add settings to `RuntimeSettings` in `src/adlc/config/settings.py`, writing tests first in `tests/unit/test_settings.py`:
  - provider keys, all `SecretStr | None`: `anthropic_api_key`, `openai_api_key`, `gemini_api_key` (`ADLC_ANTHROPIC_API_KEY`, `ADLC_OPENAI_API_KEY`, `ADLC_GEMINI_API_KEY`);
  - `model_profile` (default `default`);
  - `reviewer_mode` (`stub` | `model`, default `stub`);
  - `agent_limits`: JSON per tier `{steps, tokens, timeout_s}`. Defaults: reasoning and coding 8 / 400000 / 240; standard 6 / 200000 / 120;
  - `agent_limit_overrides`: JSON per terminal;
  - `agent_corrections` (default 2);
  - `model_outage_limit`: a duration, default 30 minutes;
  - `cost_alert_levels`: a comma list of USD amounts, default `5,20,50`.

  A validator refuses any tier or override whose `timeout_s` plus 30 s is not below `lease`
  (FR-015). Update `.env.example` (dev: `ADLC_MODEL_PROFILE=dev`, `ADLC_REVIEWER_MODE=stub`,
  key lines commented out). Keys are never logged.
- [X] T003 [P] Write failing migration tests in `tests/integration/agents/test_migration_0006.py`, following data-model.md:
  - `spec.prompt_registry`: `prompt_id` `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, `content_hash` `^sha256:[0-9a-f]{64}$`, UNIQUE (`prompt_id`, `version`);
  - `run.agent_attempt`: `kind` in (`build`, `review`); `attempt ≥ 1`; `implementation` in (`stub`, `model`); `outcome` in (`artifacts`, `clarification`, `recommendation`, `budget_exceeded`, `failed`, `model_unavailable`); `limit_reached` null or in (`steps`, `tokens`, `timeout`); `reason` at most 2,000 characters;
  - `run.model_call`: `outcome` in (`ok`, `outage`, `refusal`, `truncated`, `request_error`, `skipped`); `cost_usd numeric(14,6)` null; `cost_known` boolean; `tried jsonb NOT NULL DEFAULT '[]'` (the entries tried before this one, each `{model, outcome, reason}`);
  - `run.cost_alert`: UNIQUE (`usecase_id`, `level_usd`);
  - `run.terminal_run.model_unavailable_since timestamptz NULL`;
  - the escalation-trigger check accepts `model_unavailable` and `reviewer_failed`;
  - views `run.v_run_cost`, `run.v_terminal_cost` and `run.v_usecase_cost`;
  - the new tables are append-only for the app and owner roles; the app role has SELECT and INSERT; the views have SELECT;
  - downgrade, then upgrade again.
- [X] T004 Write `db/migrations/versions/0006_agent_runtime.py` (reusing `run.reject_mutation()`) so T003 passes. Update the expected grants in `tests/integration/test_ledger_immutability.py` and the column sets of earlier migration tests where 0006 adds columns.
- [X] T005 [P] Create the skeleton: `src/adlc/agents/__init__.py`, a stub `src/adlc/agents/README.md`, `tests/unit/agents/__init__.py` and `tests/integration/agents/__init__.py`. Add `*/adlc/agents/*` to `CORE_MODULES` in the `Makefile`.
- [X] T006 [P] Record ADR-02 (research R-15):
  - in `docs/build-plan.md`, the Models and Model gateway rows; move "LangGraph for agent graphs (006)" to the feature that introduces subagents (R-14);
  - in `docs/solution-architecture.md` §17: ADR-02 decided, with the CoE to confirm the fallback ids and the data-class approvals.

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T007 [P] Write failing spec-toolkit tests in `tests/unit/spec_toolkit/test_agent_catalogues.py`:
  - **Model catalogue:** must have a `default` profile; every profile covers every tier of `model_tiers`; every tier has at least one entry.
  - **Entries:** `provider`, `model`, `input_per_mtok`, `output_per_mtok` (number or null), `max_output_tokens`, `context_tokens` and `max_data_class` (a known data class); optional `params`.
  - **Agents catalogue:** ids unique; `implementation` is `stub` or `model`; `prompt` required for `model`; `tools[].permission` matches `^[a-z_]+:[A-Za-z0-9_.*:/-]+$`, and is split at the first colon into action and resource, so MCP scopes such as `mcp:confluence:read` (action `mcp`, resource `confluence:read`) are accepted, as feature 004 authorizes them.
  - **Cross-spec rules:** every terminal's `actors.agent.id` and `actors.reviewer` are in `agents`; the agent's `model_tier` equals the spec's; every prompt reference resolves.
  - **Prompts:** front matter `id`, `version`, `agent`, `status`; a changed body with an unchanged version is refused, as for playbooks.
- [X] T008 [P] Write failing state-machine tests in `tests/unit/orchestration/test_states.py` and `tests/unit/orchestration/test_state_properties.py` (contracts/state-machine-additions.md):
  - `agent_result` `failed` returns to `building` with `IncrementAutoRetry`, and escalates with `retry_limit` at the limit;
  - `agent_result` `model_unavailable` escalates with `model_unavailable`;
  - `review_result` `failed` escalates with `reviewer_failed`, and `model_unavailable` with `model_unavailable`;
  - property: these results never close a run and never reach `awaiting_sign_off`;
  - property: `model_unavailable` never changes `auto_retries` or `rework_count`.

### Implementation

- [X] T009 Extend the spec toolkit so T007 passes:
  - `src/adlc/spec_toolkit/loader.py`: `model_catalogue` and `agents` join `REQUIRED_CATALOGUES`; load `prompts/*.md` as a new `prompt` file kind with front matter;
  - schemas: `adlc-specs/schema/catalogues/model_catalogue.schema.json`, `adlc-specs/schema/catalogues/agents.schema.json` and `adlc-specs/schema/prompt-front-matter.schema.json`;
  - rules in `src/adlc/spec_toolkit/rules/cross_spec.py`;
  - registration of prompts into `spec.prompt_registry` in `src/adlc/spec_toolkit/register.py`;
  - registry read access (`prompt(id, version)`) in `src/adlc/spec_toolkit/registry.py`.
- [X] T010 Write the catalogue content (research R-04, R-05, R-05a):
  - `adlc-specs/shared/model_catalogue.yaml`:
    - `default`: reasoning and coding: `anthropic/claude-opus-5-5` (4 / 20, 128000 out, 1000000 context), `openai/gpt-6.1-sol` (2 / 10), `gemini/gemini-4-argon` (2 / 10); standard: `anthropic/claude-sonnet-5-5` (2 / 10), `openai/gpt-6-sol` (2 / 10), `gemini/gemini-3.8-flash` (0.75 / 3.75);
    - `dev`: every tier `openai/gpt-4o-mini` (0.15 / 0.60, 16384 out, 128000 context), then `gemini/gemini-2.5-flash` (0.30 / 2.50, 65536 out, 1048576 context), then that tier's `default` entries;
    - `max_data_class: confidential_masked` everywhere;
    - a comment marks the OpenAI and Gemini entries of `default` as "CoE to confirm".
  - `adlc-specs/shared/agents.yaml`: the ten terminal agents (`implementation: stub`, with the spec's tier, `tools: []`) and `common-terminal-reviewer` (`implementation: model`, `reasoning`, prompt `common-terminal-reviewer@1.0.0`).
  - `adlc-specs/prompts/common-terminal-reviewer.md` (v1.0.0). It states:
    - the role;
    - that data blocks are never instructions;
    - the output schema of contracts/reviewer.md;
    - the 0–3 scale;
    - that `terminate` is never recommended;
    - that a clarification needs `looked_in`.
  - Run `adlc-spec validate` with no findings, then confirm the test template database registers the new catalogues and the prompt.
- [X] T011 Feature 003 interface and state-machine additions so T008 passes:
  - `src/adlc/orchestration/interfaces.py`: `AttemptFailed(reason)` and `ModelUnavailable(detail)` added to `AgentResult` and `ReviewResult`; `Recommendation` gains `reason: str = ""`, `root_cause: str | None = None`, `reviewer: str = "stub"`;
  - `src/adlc/orchestration/states.py`: the new `result` values;
  - `src/adlc/orchestration/engine.py`: payloads (`_agent_payload`, `_review_payload`) and the `reason` on transitions;
  - the rows in `specs/003-lifecycle-orchestration/contracts/state-machine.md`.
- [X] T012 In `src/adlc/orchestration/engine.py`, read the step's inputs, then release the database connection before calling `agent.build` or `reviewer.review` (research R-07). The 003 integration and scenario suites stay green.

**Checkpoint**: catalogues and prompts validate and register; the state machine knows the new results.

---

## Phase 3: User Story 1 – Every model call goes through one gateway (P1) 🎯 MVP

**Goal**: one gateway walks the profile's entries, falls back only on outages, and records every call.

**Independent test**: with `FakeGateway`, a primary outage is answered by the next entry and recorded as `fallback`; a refusal is not passed on to another entry; entries without a key are skipped.

### Tests first

- [X] T013 [P] [US1] Write failing unit tests in `tests/unit/agents/test_catalogue.py`: profile selection (an unknown profile is refused); the tier's ordered entries; data-class rank comparison (an unresolvable ceiling counts as the highest rank); the context-window check; `max_tokens` capped at the entry's `max_output_tokens`.
- [X] T014 [P] [US1] Write failing unit tests in `tests/unit/agents/test_gateway_rules.py`, with a scripted transport (contracts/gateway.md):
  - outage (rate limit, timeout, connection, 5xx, auth) moves to the next entry;
  - refusal, truncated and request error return without fallback;
  - skips for `no_key`, `data_class` and `context` give `skipped` rows;
  - all skipped for availability gives `unavailable`; all skipped for data class or context gives `request_error`;
  - `fallback` is true only when an entry after the first runnable one answered;
  - cost from the catalogue prices, unknown price gives `cost_known=false`, failed calls cost zero unless usage was reported;
  - one record per request, outages included;
  - the answering call's `tried` lists the earlier entries with outcome and reason (US1 AC2);
  - a response without usage figures is recorded with counted tokens and `usage_estimated = true`.
- [X] T015 [P] [US1] Write failing contract tests in `tests/unit/agents/test_litellm_contract.py` (marker `litellm_contract`, `respx`). For the Anthropic, OpenAI and Gemini HTTP shapes:
  - the request body has no `temperature`, `top_p`, `top_k`, thinking budget, `reasoning_effort`, `response_format` or `tool_choice`;
  - the key is passed per call and does not appear in the process environment;
  - mapping of success with usage, a refusal (`stop_reason` `refusal`, `finish_reason` `content_filter`), a 429, a timeout and a 400 to `ok`, `refusal`, `outage`, `outage` and `request_error`.

  Importing LiteLLM makes no network call (`LITELLM_LOCAL_MODEL_COST_MAP`).
- [X] T016 [P] [US1] Add an autouse no-network guard in `tests/conftest.py`: `litellm.completion` fails the test unless it is marked `litellm_contract`.

### Implementation

- [X] T017 [US1] Implement `src/adlc/agents/catalogue.py` (T013) and `src/adlc/agents/store.py` (SQL for `run.model_call`, `run.agent_attempt` and `run.cost_alert`, each in its own short transaction).
- [X] T018 [US1] Implement `src/adlc/agents/gateway.py`:
  - the `ModelGateway` protocol and `ModelRequest` / `ModelResponse`;
  - `LiteLLMGateway`: classification per research R-02; `num_retries=0`; no Router or callbacks; telemetry off; local cost map; keys per call; one `adlc.model.call` span per request with allow-listed attributes only;
  - `src/adlc/agents/fake.py`: `FakeGateway`, with scripted outcomes per model and recorded requests.

  This makes T014 and T015 pass.
- [X] T019 [US1] Start-up check (FR-018): building the orchestrator with any `model` agent or `ADLC_REVIEWER_MODE=model` is refused when the selected profile has no keyed entry for a needed tier. The error message names the tier and the profile. Tests are in `tests/unit/agents/test_startup.py`.

**Checkpoint**: the gateway is testable alone, and every call is recorded.

---

## Phase 4: User Story 2 – Agents run inside a bounded, reproducible runtime (P1)

**Goal**: context pack and hash, validation with corrections, limits, stub agents through the runtime, deferral and escalation.

**Independent test**: identical inputs give the same pack hash; invalid output is corrected, then counted as a failed attempt; reaching the token budget escalates; a full outage defers, then escalates after the limit; the 003, 004 and 005 scenarios pass.

### Tests first

- [X] T020 [P] [US2] Write failing unit tests in `tests/unit/agents/test_context.py`:
  - the pack sections of research R-06;
  - the same inputs give the same hash; changing the spec version, profile version, a clarification answer, a playbook or a failed control changes it;
  - evidence carries the content of referenced artifact versions;
  - every untrusted text (grounding, tool output, artifacts, clarification answers, rework comments) is rendered inside `<data …>` with `</data` escaped;
  - the system prompt comes first, then stable sections, then volatile ones.
- [X] T021 [P] [US2] Write failing unit tests in `tests/unit/agents/test_output.py` (contracts/reviewer.md, builder part):
  - JSON taken from a fenced or bare block;
  - every mandatory artifact present; a conditional artifact required when its `when` holds (evaluated through a policy stub);
  - rows with exactly the declared columns for every format; undeclared artifacts refused;
  - a clarification needs at least one `looked_in` and 1–5 questions;
  - correction messages list every problem, without echoing artifact content beyond ids and column names.
- [X] T022 [P] [US2] Write failing unit tests in `tests/unit/agents/test_limits.py`: tier limits with terminal overrides; every call counts as a step, corrections included; tokens accumulate input plus output; the per-call timeout is the time left; a pack larger than the token budget gives `BudgetExceeded("tokens")` before any call.
- [X] T023 [P] [US2] Write failing integration tests in `tests/integration/agents/test_runtime.py` (`FakeGateway`, an agent switched to `implementation: model` in a test catalogue):
  - a T1 build returns valid artifacts and writes one `run.agent_attempt` row with the hashes and totals;
  - invalid output is corrected twice, then the run returns to `building` with `auto_retries + 1`, and escalates with `retry_limit` at the limit. No artifact version, control decision or review exists for the failed attempt (SC-004);
  - reaching the step, token or time limit escalates with `budget` after a single drain (SC-005), and the attempt row names the limit;
  - a step interrupted after two model calls (a fault hook before the signal is applied) keeps both `run.model_call` rows, and their cost counts in the views after the step is redone;
  - a refusal three times gives a failed attempt with no fallback rows;
  - a full outage records `deferred`, leases the run with back-off and sets `model_unavailable_since`; after 30 minutes (fake clock) the run escalates with `model_unavailable`; a later success clears the column.

### Implementation

- [X] T024 [US2] Implement `src/adlc/agents/context.py` (T020) and `src/adlc/agents/prompts.py` (prompt by id and version from the registry, with its hash).
- [X] T025 [US2] Implement `src/adlc/agents/output.py` (T021) and `src/adlc/agents/limits.py` (T022).
- [X] T026 [US2] Implement `src/adlc/agents/runner.py`: `RuntimeAgentRunner` (contracts/runtime.md).
  - The `stub` implementation wraps the existing `StubAgent` behaviour; its output is validated too (FR-024).
  - The `model` implementation runs the bounded loop with corrections.
  - Every attempt records `run.agent_attempt` and an `adlc.agent.build` span.
- [X] T027 [US2] In `src/adlc/orchestration/engine.py` and `src/adlc/orchestration/store.py`:
  - handle `ModelUnavailable`: below `model_outage_limit`, a `deferred` activity, `model_unavailable_since` set if empty, and `lease_until = now + backoff` (30 s doubling, cap 5 min, based on the deferrals since the outage began); at or over the limit, the `model_unavailable` signal;
  - handle `AttemptFailed` as the `failed` signal;
  - any other result clears `model_unavailable_since`.

  This makes T023 pass.
- [X] T028 [US2] Wire the runtime in `src/adlc/orchestration/worker.py` (`build_orchestrator`) and `src/adlc/orchestration/__main__.py`: `RuntimeAgentRunner` with `LiteLLMGateway`; test harnesses keep injecting stubs or `FakeGateway`. The 003, 004 and 005 scenario suites run with stub agents through the runtime (SC-008).

**Checkpoint**: every build attempt is reproducible, bounded and recorded.

---

## Phase 5: User Story 3 – An independent reviewer scores every run (P1)

**Goal**: a model reviewer with independent input and validated output, mapped to `Recommendation`.

**Independent test**: a T1 review scores all five items, the recommendation reaches sign-off, feature 005 writes the checklist rows, and the reviewer's requests contain none of the builder's messages.

### Tests first

- [ ] T029 [P] [US3] Write failing unit tests in `tests/unit/agents/test_reviewer_output.py` (contracts/reviewer.md):
  - scores cover exactly the terminal's checklist items, each 0–3;
  - status is `pass`, `rework` or `exception` (`terminate` refused); `rework` needs a catalogue root cause;
  - findings `item` is null or an item id; text 1–1,000 characters;
  - mapping to `Recommendation` with findings as `"item: text"`, plus `reason`, `root_cause` and `reviewer="model"`.
- [ ] T030 [P] [US3] Write failing integration tests in `tests/integration/agents/test_reviewer.py`:
  - a T1 review with a scripted model reaches `awaiting_sign_off`, and the recommendation's reason and root cause are stored on the run and in its ledger record;
  - `run.checklist_result` has five rows;
  - no recorded reviewer request contains any text the builder model received or produced (the builder scripted with marker strings);
  - output that does not fit after the corrections escalates with `reviewer_failed`;
  - a reviewer clarification moves the run to `awaiting_clarification`;
  - `ADLC_REVIEWER_MODE=stub` records `implementation = stub`.

### Implementation

- [ ] T031 [US3] Implement `src/adlc/agents/reviewer.py`: `RuntimeReviewer` built only from `ReviewContext` plus the prerequisite evidence; the `reasoning` tier; the reviewer prompt; the shared loop; `adlc.agent.review` spans and attempt rows; the stub wrapper for `stub` mode. Wire it in `build_orchestrator` according to `reviewer_mode`. This makes T029 and T030 pass.

**Checkpoint**: all P1 stories pass.

---

## Phase 6: User Story 4 – Agents ask before guessing and act only with permission (P2)

**Goal**: clarification rules, and a tool gate in front of every tool call.

**Independent test**: an allowed tool runs and is wrapped as data; a denied one is refused with the policy reason and a logged decision; a clarification without `looked_in` is corrected.

### Tests first

- [ ] T032 [P] [US4] Write failing integration tests in `tests/integration/agents/test_tool_gate.py`, using feature 004's policy engine and a `FakeTool`:
  - a T1 agent bound to `read:knowledge_base` is authorized, the tool runs, and its output reaches the next model request inside `<data source="tool:…">`;
  - a tool bound to `write:ledger.T0` is refused, the reason reaches the agent, the tool does not run, and a `run.policy_decision` row exists;
  - a call made with another run's id is refused (run scope);
  - a scripted clarification without `looked_in` is corrected, and one with it moves the run to `awaiting_clarification`.

### Implementation

- [ ] T033 [US4] Implement `src/adlc/agents/tools.py`: `ToolGate`, `ToolOutput`, `ToolRefused`, `FakeTool`. Action and resource come from the binding's `permission`. Add the tool round to the loop in `runner.py`. This makes T032 pass.

---

## Phase 7: User Story 5 – Cost and traces are visible per run and use case (P2)

**Goal**: cost views, alerts and content-free spans.

**Independent test**: after a scripted T0–T2 walk, the view totals equal the sum of the calls, alerts fire once per level, and spans have only allow-listed attributes.

### Tests first

- [ ] T034 [P] [US5] Write failing integration tests in `tests/integration/agents/test_cost.py`:
  - `run.v_run_cost`, `run.v_terminal_cost` and `run.v_usecase_cost` equal the sums of `run.model_call` to the cent (SC-007), with unknown-price calls counted separately and fallback answers counted;
  - crossing `5` then `20` USD writes one `run.cost_alert` per level, never twice;
  - SC-001: a full T0–T8 walk with `ADLC_REVIEWER_MODE=model` and `FakeGateway` gives exactly one `run.model_call` row per gateway request the fake received, and every row has provider, model, tokens and cost (or `cost_known = false`).
- [ ] T035 [P] [US5] Write failing tests in `tests/unit/agents/test_spans.py` with an in-memory span exporter: `adlc.model.call`, `adlc.agent.build` and `adlc.agent.review` carry only allow-listed attributes, each value at most 200 characters. The marker strings used in prompts and outputs never appear in any span.

### Implementation

- [ ] T036 [US5] Implement `src/adlc/agents/cost.py` (cost per call, alert check after each recorded call, and readers over the three views, for features 007 and 013), and the span attribute allow list in `gateway.py`, `runner.py` and `reviewer.py`. This makes T034 and T035 pass.

---

## Phase 8: Polish and cross-cutting

- [ ] T037 [P] Extend `tests/unit/test_no_hardcoded_values.py` so `src/adlc/agents/` is also checked for terminal ids, role ids, route destinations, and provider or model ids (taken from `model_catalogue.yaml`). Add a check that `litellm` is imported only in `src/adlc/agents/gateway.py` (FR-001).
- [ ] T038 [P] Write `src/adlc/agents/README.md`, covering:
  - the gateway rules;
  - profiles (`dev` puts GPT-4o mini first);
  - keys;
  - the context pack;
  - validation;
  - limits and the lease;
  - deferral;
  - the reviewer;
  - the tool gate;
  - cost;
  - how feature 008 switches an agent to `implementation: model`.

  Also note GPT-4o mini's retirement on 2027-01-14.
- [ ] T039 Run the 003, 004, 005 and 006 scenario and integration suites 10 times in a row, and record the result (SC-008).
- [ ] T040 Measure runtime overhead per attempt, excluding model time, with `FakeGateway` (SC-009: under 200 ms), in `tests/integration/agents/test_overhead.py`.
- [ ] T041 Run `make check` and fix any failure, including the 80% core coverage gate that now includes `agents/`.
- [ ] T042 Live check in dev (quickstart §5), only if the user provides `ADLC_OPENAI_API_KEY`. With `ADLC_MODEL_PROFILE=dev` and `ADLC_REVIEWER_MODE=model`, run `make up` and `scripts.demo_drive`. Then check that:
  - the reviews come from `openai/gpt-4o-mini` with `fallback = false`;
  - costs appear in `run.v_usecase_cost`;
  - `adlc.model.call` spans appear in Jaeger without content;
  - `adlc-ledger verify` reports verified.

  Without a key, run the stack with `ADLC_REVIEWER_MODE=stub` and record that the live model
  check was skipped.

---

## Dependencies and execution order

- **Phases:** Phase 1, then Phase 2, then the stories.
- **US1 first:** US2 and US3 use the gateway.
- **US2** builds on US1.
- **US3** needs US1 and the runner loop from T026.
- **US4** needs US2's loop (T026).
- **US5** needs US1's records. It can run in parallel with US3 and US4.
- **Phase 8** comes last.

## Parallel examples

- **Phase 1**: T003, T005 and T006 together.
- **Phase 2**: T007 and T008 together.
- **US1**: T013, T014, T015 and T016 together.
- **US2**: T020, T021, T022 and T023 together.
- **US3**: T029 and T030 together.
- **US5**: T034 and T035 together.

## Implementation strategy

1. **MVP**: Phases 1–3. One recorded gateway with correct fallback.
2. **Runtime**: Phase 4. Stub agents run through it, and all scenario suites pass.
3. **Reviewer**: Phase 5. The first real model judgement.
4. **Permissions and cost**: Phases 6–7.
5. **Polish**: Phase 8.

Run `make check` and commit at every checkpoint.
