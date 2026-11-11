# Quickstart: Terminal Agents T0–T2

## 1. Offline (no model provider)

```bash
make check                                   # includes the 008 unit, integration and scenario tests
```

The scenario suite replays the three reference use cases from `tests/fixtures/replays` with no
provider. To replay them against the running stack, use the Compose commands in
`contracts/replay.md` (`--recording /rec`).

**Expect**: each of the three reference use cases reaches T2 sign-off. The report lists every
mandatory artifact present, all blocking controls passing, the reviewer's recommendation, the
citations given, and the agent, prompt and playbook hashes.

## 2. Live stack

**Settings in `.env`:**
- `ADLC_MODEL_PROFILE=dev` and `ADLC_OPENAI_API_KEY` (from feature 006);
- `ADLC_KNOWLEDGE_TOKEN`, a random secret;
- `ADLC_REVIEWER_MODE=model`.

```bash
make up                                      # adds the knowledge container
uv run adlc-spec register adlc-specs         # registers T0–T2 2.0.0, prompts and playbooks
open http://localhost:8501
```

**The walk:**
1. Sign in as the business owner and submit a use case (for example the travel claims text from
   `data/reference_usecases/travel-claims.yaml`).
2. Open T0 when it reaches sign-off. Check:
   - the drafted artifacts;
   - the Citations section, which shows sources from SharePoint `/strategy`, `/policies`,
     Confluence `/business-capabilities` and the portfolio only;
   - the reviewer's recommendation.
3. If the agent asks a clarification, it is in the business owner's inbox. Answer it; the same run
   resumes.
4. Pass T0 (the business owner), then T1 (the product owner and the business owner), and check T2.

**Live replay:**

```bash
# inside Compose, with the orchestrator worker stopped (contracts/replay.md)
adlc-replay --profile dev --baseline <earlier report dir>
```

**Expect** (SC-001, SC-005, SC-006):
- at least 2 of 3 use cases pass every blocking control on the first attempt;
- each terminal reaches sign-off within 5 minutes;
- the total cost is under 1 USD.

**Jaeger:** `adlc.agent.tool` and `adlc.agent.retrieval` spans show each knowledge call, with no
content.

## 3. Reset after the spec change

Use cases pinned to T0–T2 1.0.0 cannot rebuild those terminals (research R-08). Start new use cases
after registering 2.0.0.
