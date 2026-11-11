# adlc.agents

The agent runtime (feature 006; SA §7). Every lifecycle agent and the common reviewer run through
it, behind feature 003's `AgentRunner` and `Reviewer` interfaces. Specification:
`specs/006-agent-runtime/`.

## Modules

| Module | Purpose |
| --- | --- |
| `catalogue.py` | Model catalogue (profiles, tiers, prices, limits, data-class approvals) and agents catalogue, read from the spec registry |
| `gateway.py` | `RoutingGateway` (the rules), `LiteLLMTransport` (the only code that calls a provider), outcome classification |
| `fake.py` | `FakeGateway` and `FakeTransport`: the real rules over scripted replies, for tests |
| `context.py` | Context pack, its hash, `<data>` blocks, message rendering, prerequisite evidence |
| `prompts.py` | Prompts, playbooks and checklists from the spec folder, checked against their registered hashes |
| `output.py` | Builder and reviewer output validation, correction messages |
| `limits.py` | Step, token and time limits per tier, with terminal overrides |
| `runner.py` | `RuntimeAgentRunner` and the bounded model loop shared with the reviewer |
| `reviewer.py` | `RuntimeReviewer`: independent input, scores, recommendation |
| `tools.py` | `ToolGate`: every tool call is authorized by feature 004 first; tools get the run's context (`ToolContext`) and describe themselves to the model |
| `knowledge.py` | `KnowledgeTool` (one source operation), `knowledge_tools` (from bindings `<source>_<operation>` with permission `mcp:<source>:read`), `McpCaller` (the MCP client) |
| `citations.py` | `SqlRetrievalLog`: every knowledge result returned to an agent, in `run.knowledge_retrieval` |
| `replay.py`, `replay_cli.py` | `adlc-replay`: reference use cases through the grounded terminals, from recordings or live, with a quality report |
| `cost.py` | Cost alerts and cost readers |
| `store.py` | SQL for `run.model_call` and `run.agent_attempt` |
| `startup.py` | Refuses to start when a needed tier has no keyed model |
| `telemetry.py` | Span attribute allow list |
| `wiring.py` | `build_runtime`, used by the orchestrator process and the test harness |

## Models and profiles

- **The tier comes from the spec.** An agent asks for a model tier (`reasoning`, `coding` or
  `standard`), taken from the terminal spec. It never names a model.
- **The catalogue gives the order.** `adlc-specs/shared/model_catalogue.yaml` maps each tier to an
  ordered list of models, per profile:

  | Profile | Order | Used in |
  | --- | --- | --- |
  | `default` | Anthropic first (Claude Opus 5.5 for `reasoning` and `coding`, Claude Sonnet 5.5 for `standard`), then OpenAI, then Gemini | Production (ADR-02) |
  | `dev` | OpenAI GPT-4o mini, then Gemini 2.5 Flash, then the `default` models | Development tests |

  OpenAI retires the dated GPT-4o mini snapshot on 2027-01-14; move `dev` to another small model
  before then. The OpenAI and Gemini entries of `default` are marked "CoE to confirm".
- **The environment selects.** `ADLC_MODEL_PROFILE` selects the profile.
- **Keys:** `ADLC_ANTHROPIC_API_KEY`, `ADLC_OPENAI_API_KEY` and `ADLC_GEMINI_API_KEY`, all from
  the environment only. They are passed per call and are never logged, traced or stored.

## Gateway rules

1. **Skips.** Walk the tier's entries in order, and skip an entry when:
   - it has no key;
   - its approved data class ranks below the run's ceiling. An unresolved ceiling, such as a
     resolver, counts as the highest rank, so the check fails closed;
   - the request does not fit its context window.
2. **Fallback only on outages.** Move to the next entry only on an outage: a rate limit, a
   timeout, a connection or server error, or an authentication error.
3. **No fallback otherwise.** A refusal, a truncated or empty answer, or a request error returns
   at once. The runtime asks the same model again (a correction) and then fails the attempt. A gate
   must never pass because another model was more willing. Anthropic's server-side refusal
   fallback is not enabled.
4. **When nothing answers.** If no entry answered because of keys or outages, the result is
   `unavailable`. If every entry was skipped for data class or context, it is `request_error`,
   because waiting cannot help.
5. **Records and traces.** Every request writes one `run.model_call` row, including outages and
   skips. Each row has `tried`, tokens, cost (`NULL` when the price is unknown), `usage_estimated`
   and `fallback`. Every request also gets one `adlc.model.call` span without content.

## LiteLLM

`litellm==1.106.5` is pinned. LiteLLM is imported lazily (the import takes seconds), with the
local cost map, no telemetry and no callbacks. Each call uses `num_retries=0`; the gateway owns
retries and the order.

**Request settings.** The gateway never sends sampling settings, a thinking budget,
`reasoning_effort`, `response_format` or `tool_choice`. Claude Opus 5.5 and Sonnet 5.5 reject some
of these, and LiteLLM's JSON mode uses a forced tool choice, which they also refuse.

**How replies map:** observed with mocked HTTP and recorded in research R-17.

| Reply | Outcome |
| --- | --- |
| Anthropic `refusal` | `content_filter`, a refusal |
| `length`, or an empty answer | truncated |
| A malformed reply (e.g. no usage), which LiteLLM wraps as a connection error | detected from the exception chain; a request error, not an outage |

`tests/unit/agents/test_litellm_contract.py` checks request bodies and reply mapping for the three
providers with respx. Run it again before any LiteLLM upgrade.

## Context pack

**Contents:**

- agent and prompt hash;
- the pinned spec (artifacts, controls);
- use-case facts;
- the profile version the run opened with;
- prerequisite evidence: the latest record of each terminal the prerequisites name, with the
  content of its artifact versions;
- trigger;
- answered clarifications;
- failed controls;
- previous artifacts;
- playbooks (hashed).

**Hash.** The hash is computed over these inputs only, with no run id or times. Each attempt
records it with the agent version, prompt hash and playbook hashes.

**Rendering:**

- The system prompt and runtime rules come first, then the stable sections (spec, playbooks),
  then the volatile ones.
- Everything the platform did not write itself sits inside `<data source="...">` blocks, with
  `</data` escaped: intake, evidence, artifacts, clarification answers, comments, tool output.
- The rules state that data is never an instruction.

## Output, limits and attempts

**Output rules:**

- Builders answer `{"artifacts": {...}}`, `{"clarification": {...}}` or `{"tool": {...}}`.
- Every mandatory artifact must be present. A conditional artifact is required when its
  condition holds.
- Rows have exactly the declared columns. A clarification must say where the agent looked.
- Output that does not fit gets up to `ADLC_AGENT_CORRECTIONS` correction rounds. After that the
  attempt fails, and the run uses the same retry counter as failed blocking controls.

**Limits:**

- Each tier has a step, token and time limit (`ADLC_AGENT_LIMITS`), with per-terminal overrides
  (`ADLC_AGENT_LIMIT_OVERRIDES`).
- Every call is a step. Reaching a limit escalates the run with trigger `budget`.
- Each timeout plus 30 s must be shorter than the worker lease; the settings check this at
  start-up.

**Stub agents.** Stub agents (terminal agents until feature 008) run through the same runtime.
The pack is built and hashed and their output is validated, but no model is called.

**Outages:**

- During a full outage the engine defers the run: 30 s back-off, doubling up to 5 minutes.
- The outage does not count as a retry.
- The run escalates with `model_unavailable` once `ADLC_MODEL_OUTAGE_LIMIT` (default 30 minutes)
  has passed.

## Reviewer

**Input.** The reviewer sees only:

- the checklist (ids and text);
- the artifacts;
- the control results;
- the prerequisite evidence;
- answers to its own questions.

It never sees builder messages.

**Output:**

- It scores every item from 0 to 3.
- It recommends `pass`, `rework` (with a catalogue root cause) or `exception`, never
  `terminate`.
- It may ask a clarification instead.
- Findings become `"item: text"` for feature 005's checklist rows. The reason and root cause are
  stored with the recommendation.

**Failure.** Output that still does not fit after the corrections escalates with
`reviewer_failed`.

**Mode.** `ADLC_REVIEWER_MODE=stub` (the default) keeps the stub reviewer. Either way the attempt
is recorded with its implementation.

## Tools

`ToolGate` authorizes every call with feature 004's run-scoped `authorize`. The action and
resource come from the tool binding's `permission` in `agents.yaml`, for example
`read:knowledge_base` or `mcp:jira:read`.

- A refused call is not made; the refusal and its reason go back to the agent.
- Output reaches the model as a data block.
- Real tools (MCP servers) arrive with features 008 and 010.

### Knowledge tools (feature 008)

- **Bindings.** An agent gets `<source>_search` and `<source>_read` for each source that its
  terminal names both in `tool_scopes` and in its grounding entries (FR-002). The model is told
  each tool's name, description and the arguments it may set.
- **Scope and class.** `KnowledgeTool` passes on only the model's allowed arguments and adds the
  terminal's grounding scope and maximum data class from the pinned spec. A source without a
  grounding entry is not called.
- **Failures.** An unreachable server (10 s timeout) returns "knowledge source unavailable:
  <source>" to the agent, with no retry inside the attempt.
- **Records.** Every result returned is written to `run.knowledge_retrieval` (append-only) before
  the model sees it.
- **Startup.** The orchestrator refuses to start when an agent has knowledge tools and
  `ADLC_KNOWLEDGE_TOKEN` is not set.

## Citations (feature 008)

A builder may add `"citations"` beside `"artifacts"`: `artifact`, optional `row`, `source`,
`document` and `section`. Citations are optional; each one given must match a retrieval of the
same attempt, or the answer fails validation and is corrected. The content hash and retrieval id
come from the retrieval, never from the model. The engine stores them in `run.artifact_citation`
with the artifact version they support. The run detail (feature 007) and the reviewer's input
show them; the reviewer never sees the builder's tool calls.

## Replay (feature 008)

```bash
uv run adlc-replay --recording tests/fixtures/replays          # no provider
uv run adlc-replay --profile dev --record tests/fixtures/replays # live, and save the replies
uv run adlc-replay --profile dev --baseline reports/replays/<earlier>
```

The replay acts as the people of the account file and refuses to run while another orchestrator
worker is active. Recordings are `<use case>/<agent>.jsonl`, replies only; the agent is recognised
by its registered prompt. The report (`report.json`, `report.md`) lists, per use case and terminal:
mandatory artifacts, blocking controls, whether the first attempt was clean, the recommendation
(and a change against the baseline), clarifications, citations, steps, tokens, cost, and the
agent, prompt, playbook and model versions.

## Traces

| Span | Covers | Attributes |
| --- | --- | --- |
| `adlc.agent.build` | The engine's build step | — |
| `adlc.agent.attempt` | One build attempt by the runtime | outcome, steps, tokens, corrections, limit reached |
| `adlc.reviewer.review` | The engine's review step | — |
| `adlc.agent.review` | One review attempt | as for build attempts |
| `adlc.agent.tool` | One tool call through the gate (feature 008) | run, use case, terminal |
| `adlc.agent.retrieval` | Writing a knowledge call's retrieval records (feature 008) | run, terminal |
| `adlc.model.call` | One gateway request | tier, provider, model, tokens, cost, outcome, fallback, latency |

Attributes come from the allow list in `telemetry.py`, each value at most 200 characters, and
never include content.

## Cost

Totals per run, terminal and use case come from the views `run.v_run_cost`, `run.v_terminal_cost`
and `run.v_usecase_cost`, or from `cost.run_cost`, `terminal_cost` and `usecase_cost`. These
readers serve features 007 and 013.

`ADLC_COST_ALERT_LEVELS` (USD per use case, default `5,20,50`) writes one `run.cost_alert` per
level reached. Alerts never stop runs.

## Moving an agent to a model (feature 008)

1. Write its prompt in `adlc-specs/prompts/<agent-id>.md`, with front matter `id`, `version`,
   `agent` and `status`.
2. In `agents.yaml`, set `implementation: model` and `prompt: {id, version}`, and add its tool
   bindings.
3. Run `adlc-spec validate` (rules V-27 to V-30), then register.

No runtime code changes.

## Data ceilings

A terminal's `authorities.data_access.max_class` is either a data class or a resolver.

- **Resolvers.** A resolver in `data_classes.yaml` names a `source` artifact column, for example
  `per_T2_prod_design` takes `T2.data_strategy.classification`. The ceiling is then the
  highest-ranked class in that column of the use case's latest record.
- **Fail closed.** If the record is missing, the column is empty, or any value is not a known
  class, the resolver stays unresolved. It then counts as above every approval, so no model
  qualifies.
- **Validation.** Rule V-31 checks that the source is a declared artifact column.
