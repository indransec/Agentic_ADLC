# Contract: Model Gateway

```text
ModelGateway.complete(request: ModelRequest) -> ModelResponse

ModelRequest:
  tier:         str
  data_class:   str            # the run's ceiling (terminal authorities.data_access.max_class)
  messages:     list[Message]  # system first; data blocks already wrapped
  max_tokens:   int
  timeout_s:    float          # the time left in the attempt
  ids:          {run_id, usecase_id, terminal_id, agent_id, attempt_ref}
  prompt_hash:  str
  context_hash: str

ModelResponse:
  outcome:    ok | refusal | truncated | request_error | unavailable
  text:       str              # empty unless the outcome is ok
  model:      str              # the entry that answered (or was last tried)
  provider:   str
  fallback:   bool
  tokens_in:  int
  tokens_out: int
  cost_usd:   Decimal | None
  tried:      [{model, outcome, reason}]   # entries before the one that answered
```

## Rules

1. **Order:** the gateway walks the tier's entries in the order of the catalogue profile
   selected by `ADLC_MODEL_PROFILE` (default `default`; `dev` puts Gemini 2.5 Flash first). It
   skips an entry:
   - with no key: a `skipped` call row with reason `no_key`;
   - whose `max_data_class` ranks below the request's `data_class`: a `skipped` row with reason
     `data_class`.
2. **Outcomes per call:**
   - `outage`: move to the next entry.
   - `refusal`, `truncated` and `request_error`: return immediately. Never move to another
     entry.
3. **Full outage:** when no entry answers, return `outcome = unavailable`.
4. **Records:** every request writes one `run.model_call` row in its own transaction, including
   outage rows. After each recorded `ok` call, the use case's cost alerts are checked.
5. **Request body:** the gateway never sends `temperature`, `top_p`, `top_k`, a thinking budget,
   `reasoning_effort`, `response_format` or `tool_choice`, beyond what the entry's `params`
   explicitly holds.
6. **Keys:** keys come from settings (`ADLC_ANTHROPIC_API_KEY`, `ADLC_OPENAI_API_KEY`,
   `ADLC_GEMINI_API_KEY`) and are passed per call. They are never logged, traced or stored.
7. **Trace:** one span per request, `adlc.model.call`, with the attributes of FR-023. It never
   carries message text.

## Implementations

| Implementation | Use |
| --- | --- |
| `LiteLLMGateway` | Production (R-01, R-02) |
| `FakeGateway` | Tests: outcomes scripted per model, with recorded requests for checks |
