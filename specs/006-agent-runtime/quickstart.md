# Quickstart: Agent Runtime

How to check feature 006 end to end. Tests use the fake gateway and need no provider keys.

## 1. Specs and catalogues

```bash
uv run adlc-spec validate adlc-specs        # model_catalogue, agents and prompts validate
```

**Expect**: no errors. Breaking any of these gives a finding naming the file and path:

- every tier has at least one entry;
- every terminal's agent and reviewer exist in `agents.yaml`, with the spec's tier;
- every prompt reference resolves.

## 2. Unit and contract tests

```bash
uv run pytest tests/unit/agents -q
uv run pytest -m litellm_contract -q        # LiteLLM request and response mapping, mocked HTTP
```

**Expect**:

- **Gateway:** outages move to the next entry; refusals do not. No sampling settings or thinking
  budget appear in the Anthropic request body.
- **Validation:** output that does not fit is caught.
- **Context pack:** the hash is the same for identical inputs.

## 3. Runtime in the orchestrator (integration)

```bash
uv run pytest tests/integration/agents -q
```

**Expect**:

- a T1 run with the model reviewer and a scripted model gives a recommendation that scores the
  five T1 items, and feature 005 records the checklist rows;
- budget, step-limit and timeout breaches escalate;
- a full outage defers the run, then escalates after the outage limit;
- `run.model_call`, `run.agent_attempt` and the cost views add up.

## 4. Existing scenarios (SC-008)

```bash
uv run pytest tests/scenario -q             # stub terminal agents through the runtime
make check
```

## 5. Live stack (optional, real models)

Run this only with provider keys and the CoE's agreement to spend.

```bash
# .env: ADLC_ANTHROPIC_API_KEY=..., ADLC_REVIEWER_MODE=model
make up && uv run python -m scripts.demo_drive
```

**Expect**: the reviewer's recommendations come from `anthropic/claude-opus-5-5`, with costs in
`run.v_usecase_cost` and `adlc.model.call` spans in Jaeger without prompt text. Without keys,
leave `ADLC_REVIEWER_MODE=stub`; the demo runs as before.
