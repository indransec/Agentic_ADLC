# Research: Terminal Agents T0–T2

## R-01 The knowledge service is a real MCP server

**Decision**:
- **Server:** a separate process and container (`knowledge`) built on the MCP Python SDK
  (`mcp==1.30.0`, `FastMCP`, streamable HTTP, stateless, JSON responses).
- **Endpoints:** one MCP endpoint per catalogue source it serves, at `/mcp/<source>` (for example
  `/mcp/confluence`), so each enterprise source keeps its own MCP identity.
- **Tools:** each endpoint has two tools, `search` and `read` (contracts/knowledge-mcp.md).
- **Client:** the platform calls the server through the SDK's streamable-HTTP client.

**Rationale**:
- SA §13 and constitution VII: mocks implement the same tool names and schemas as the real
  servers. Replacing a source with a real Confluence or SharePoint MCP server is then a
  configuration change.
- A separate container keeps documents out of the platform process.

**Why 1.30.0 and not 2.x**:
- **Age:** 1.30.0 was released 2026-09-07; 2.3.0 was released 2026-10-02. Both are older than two
  weeks.
- **Dependencies:** 1.30.0 uses `httpx`, which the platform already has. 2.x brings a new HTTP
  stack (`httpx2`) and a split `mcp-types` package.
- **Verified:** the 1.x server (`FastMCP.streamable_http_app`) and client
  (`streamablehttp_client`, `ClientSession`) import and start under Python 3.12.

**Alternatives**:
- An in-process tool reading the folder directly: not MCP, so the real servers could not be
  swapped in by configuration.
- One MCP endpoint for all sources: hides which source a document came from from the policy
  engine.

## R-02 Tools receive the run's context; scope is enforced on both sides

**Decision**:
- **Tool interface:** feature 006's `Tool` gains a context argument:
  `call(arguments, context)`. The context holds the run, use case, terminal and pinned spec. This
  is an additive change, and `FakeTool` is updated.
- **Knowledge adapter:** `KnowledgeTool(source, operation)` is generic. It:
  - takes only the model's allowed arguments (`query` and `limit`, or `document` and `section`);
  - adds the terminal's grounding scope and maximum data class, read from the pinned spec;
  - calls `${ADLC_KNOWLEDGE_URL}/mcp/<source>`.
- **Order of checks:** the policy engine authorizes first, through `ToolGate` (`mcp:<source>:read`
  against `tool_scopes`). The server then enforces scope and data class again, so a request
  outside them returns nothing.
- **Service token:** the server requires a bearer service token (`ADLC_KNOWLEDGE_TOKEN`) and
  refuses to start without one.

**Rationale**: constitution IV and XI (every call authorized; deny by default; defence in depth).
The model never chooses its own scope.

## R-03 Grounding scope: path prefixes or collections

**Decision**: a terminal's `playbooks.grounding` entries give its scope per source. Each entry's
`scope` is a comma-separated list, and each item is one of:

- **Path prefix** (starts with `/`, e.g. `/strategy`): documents under that folder of the source.
- **Collection label** (anything else, e.g. `reference architectures` or `related epics`):
  documents whose front matter `collections` contains the label (case-insensitive).

**Bindings:** an agent gets tools only for sources that are both in `tool_scopes` and in its
grounding entries. Today, for example, T1 and T2 may read SharePoint but have no SharePoint
grounding, so they get no SharePoint tool. The CoE can widen this later by adding a grounding
entry, a spec change with no code change.

**Rationale**: FR-002 and FR-010. The labels in the specs are kept as written, and the synthetic
knowledge set uses them.

## R-04 Citations and retrievals are append-only records

**Decision**:
- **Retrievals:** every knowledge result returned to an agent is recorded in
  `run.knowledge_retrieval`: run, attempt, step, source, operation, query or document, section,
  content hash, data class, synthetic flag and time.
- **Citations in the output:** the builder's output gains an optional `citations` list next to
  `artifacts`. Each entry has `artifact`, an optional `row` (index), `source`, `document` and
  `section`.
- **Validation:** each citation must match a retrieval of the same attempt (retrievals from
  earlier attempts do not count); if not, output validation fails and the normal corrections
  apply. Its content hash is taken from the retrieval,
  never from the model.
- **Storage:** citations are stored in `run.artifact_citation`, linked to the artifact version
  they support.
- **Immutability:** both tables are append-only, with the same trigger as the ledger tables.
- **Ledger record:** its content (feature 005, v2) is unchanged. A citation is bound to its
  artifact version's content hash, and the version is in the ledger record.

**Rationale**: the clarification answers (citation records; optional, but valid when given). The
retrieval log also serves FR-021.

**Alternative**: citations inside the ledger record content (a v3 record). That would be stronger
binding but a format change. It is left for the CoE to decide later.

## R-05 Tools and citations are described to the model generically

**Decision**:
- **Tools section:** the builder's request gains a "tools" section, listing the agent's bindings,
  each with the description and argument schema the tool gives (`Tool.describe()`).
- **Output instruction:** it shows the tool request shape (`{"tool": {"name", "arguments"}}`) and
  the optional `citations` list.
- **No terminal code:** nothing here names a terminal; the content comes from the catalogue and
  the tools.

## R-06 Keyword search over sections

**Decision**:
- **Index:** at start-up, the server reads the folder and splits each Markdown document into
  sections at its headings, then indexes the sections with BM25 (implemented in a few lines, no
  new dependency).
- **`search(query, limit=5)`:** returns up to `limit` (at most 10) results in scope. Each result
  has source, document, section, title, a snippet of at most 1,000 characters and the content
  hash.
- **`read(document, section?)`:** returns a section, or the document's outline, capped at 8,000
  characters with a "cut" note.
- **Total cap:** feature 006 caps any tool output at 20,000 characters.

**Rationale**: the spec assumption (keyword search; vector search only if replays show the need).

## R-06a Knowledge server failures

**Decision**: a connection error, timeout (10 s) or server error on a knowledge call returns a
tool error to the agent ("knowledge source unavailable: <source>"), with no retry inside the
attempt. The agent continues without it or asks a clarification; its prompt forbids inventing
sources. The retrieval log records nothing for a failed call; the span records the failure.

## R-07 Knowledge documents and the synthetic set

**Decision**:
- **Format:** Markdown with front matter:
  - `title`;
  - `data_class` (an id from `data_classes.yaml`);
  - `synthetic: true|false`;
  - `collections: [...]`;
  - `version`.
- **Missing data class:** a document without a valid `data_class` is not served (fails closed).
- **Layout:** `<ADLC_KNOWLEDGE_DIR>/<source>/<path>.md`. The demo set lives at `data/knowledge/`
  and is labelled synthetic.
- **Demo content:** for a fictional insurer:
  - business capabilities;
  - strategy and policies (including the data and AI policies);
  - an agent portfolio (one entry similar to Travel Claims);
  - process documents and SOPs (claims handling);
  - related epics;
  - platform standards;
  - reference architectures and ADRs;
  - the approved MCP server and tool list.
- **Test-only documents:** an injection document and an over-class (confidential) document are
  in the test fixtures, not in the demo set.
- **Coverage:** every grounding scope item of T0–T2 (path prefix or collection label) has at
  least one document; a unit test checks this against the registered specs.

## R-08 Prompts, playbooks and spec versions

**Decision**:
- **Prompts:** three prompts, `adlc-specs/prompts/t0-intake-agent.md`, `t1-requirements-agent.md`
  and `t2-architect-agent.md`. Each has front matter (id, version, agent) and a body stating the
  role, method (use the playbooks, ground and cite, build on evidence, ask instead of guessing,
  address the role that owns the fact) and the data rule.
- **Agents catalogue:** goes to 1.1.0. The T0–T2 agents become `implementation: model`, with a
  prompt and knowledge tool bindings (R-03).
- **Playbooks:** the nine playbooks get real procedures, each with at least: purpose; the steps
  per artifact it covers; the scales or criteria it applies (for example the suitability score
  scale and the risk tier criteria); and when to ask a clarification. Changed content needs a new version (the
  registry refuses changed content under an existing version), so each moves to 1.1.0 with
  `status: active`.
- **Terminal specs:** the T0, T1 and T2 specs pin their playbook versions, so they move to 1.1.0,
  referencing the new playbooks. Nothing else in the specs changes.
- **Pinned use cases:** new use cases pin 1.1.0. A use case already pinned to 1.0.0 cannot build
  T0–T2 again, because the 1.0.0 playbook text is no longer on disk. That is acceptable: there are
  no production use cases yet, and dev data is reset (quickstart).

## R-09 Clarification addressee

**Decision**: the output validation of feature 006 checks a clarification's `addressed_role`: it
must be one of the terminal's human roles, or empty (feature 003's default then applies). An
unknown role leads to a correction round. The prompts tell agents to address the role that owns the
fact (clarification answer 3).

## R-10 Reference use cases, recordings and the quality report

**Decision**:
- **Reference set:** `data/reference_usecases/`, one YAML file per use case. Each holds a name,
  intake text, prepared clarification answers (matched by role), the approver fields typed at pass
  (e.g. risk tier) and the expected risk tier. The set:
  - Travel Claims Assistant (pilot, medium tier);
  - IT service desk triage (low tier);
  - loan pre-screening assistant (high tier).
- **Replay tool:** `adlc-replay` (Typer, `src/adlc/agents/replay.py`). It drives each reference
  use case through T0–T2 using the services:
  - submit;
  - drain the worker;
  - answer clarifications from the file;
  - pass each terminal with the approvers the sign-off rule needs.

  It stops after T2's review and writes the report.
- **Modes:**
  - `--profile <name>` replays live;
  - `--record <dir>` also saves every model reply as a recording;
  - `--recording <dir>` replays from recordings through `FakeTransport`, with no provider.
- **Recordings:** they are keyed by agent and call order, not by prompt hash, so a prompt change
  still replays. The committed recordings under `tests/fixtures/replays/` are made once, live,
  with the `dev` profile.
- **Report** (`reports/replays/<timestamp>/report.json` and `report.md`, git-ignored), per use
  case and terminal:
  - mandatory artifacts present;
  - blocking controls passed;
  - reviewer recommendation, reason and root cause;
  - steps, tokens and cost;
  - agent, prompt, playbook and model versions and hashes.

  `--baseline <dir>` marks where the recommendation changed.

**Rationale**: FR-018 to FR-020; SA §7.4.

## R-11 What the approver and reviewer see

**Decision**:
- **Run detail:** feature 007's run detail adds `citations` per artifact (source, document,
  section and row) and a Citations section on the run page, as plain text.
- **Reviewer:** the reviewer's input includes the citations with the artifacts. They are evidence,
  not builder reasoning (SA §7.2 point 5).

## R-12 Settings, container and traces

**Decision**:
- **Platform settings:**
  - `ADLC_KNOWLEDGE_URL` (default `http://knowledge:8020`);
  - `ADLC_KNOWLEDGE_TOKEN` (a secret, required when any agent has knowledge bindings).
- **Server settings:** `ADLC_KNOWLEDGE_DIR`, `ADLC_KNOWLEDGE_TOKEN` and `ADLC_SPEC_DIR` (for the
  data class catalogue).
- **Container:** `knowledge` in Compose, using the same image, port 8020 inside only, with a health
  check. The orchestrator depends on it starting.
- **Traces:** each knowledge call adds an `adlc.tool.call` span with run, terminal, tool, source,
  outcome and result count, and never content (FR-021). The server logs request counts only.

## R-13 Limits for tool use

**Decision**: tool calls count as steps (feature 006). The reasoning tier's step limit must leave
room for several searches. If it is too low, the CoE raises it per terminal through
`ADLC_AGENT_LIMIT_OVERRIDES` (configuration, not code). The quickstart uses the recorded replays
to show the steps actually used.

## R-14 Testing approach

**Decision**:
- **Unit:**
  - scope resolution;
  - BM25 search and section splitting;
  - the data class filter;
  - citation validation against retrievals;
  - addressee validation;
  - tool descriptions in the request.
- **Integration:**
  - the knowledge server in-process (Starlette test client) over a fixture folder;
  - `KnowledgeTool` through the real MCP client against it;
  - T0–T2 runs on the orchestration harness with `FakeTransport` recordings (US1–US4);
  - injection and refusal tests.
- **Scenario:** `adlc-replay --recording` over the three reference use cases (SC-001).
- **Live:** a `dev` profile replay, recorded in tasks (SC-001, SC-005, SC-006).
