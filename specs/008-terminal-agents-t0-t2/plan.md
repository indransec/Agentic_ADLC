# Implementation Plan: Terminal Agents T0–T2

**Branch**: `008-terminal-agents-t0-t2` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-terminal-agents-t0-t2/spec.md`

## Summary

The T0, T1 and T2 agents become model agents. This is content plus registry entries: three prompts,
nine real playbooks, the agents catalogue at 1.1.0, and the T0–T2 specs at 1.1.0 (playbook
references only).

They ground on a new **knowledge MCP server**, a separate `knowledge` container on the MCP Python
SDK. It serves one MCP endpoint per enterprise source (wiki, document library, portfolio, backlog,
architecture repository, MCP registry) over a local document folder, with a synthetic enterprise
knowledge set for the demo.

**Generic runtime changes (feature 006 code, no terminal names):**
- **Tools get context:** tools receive the run's context, and a generic `KnowledgeTool` adds the
  terminal's grounding scope and maximum data class after `ToolGate` has authorized the call.
- **Tools are described:** the model is told about its tools.
- **Citations:** the builder may return citations, which are validated against what it retrieved.
- **Records:** retrievals and citations are append-only records (migration 0008).
- **Addressee check:** a clarification's addressee must be one of the terminal's roles.

**Elsewhere:**
- **Inbox (007):** the run detail shows citations.
- **Quality:** a replay tool (`adlc-replay`) runs three reference use cases through T0–T2, from
  recordings or live, and writes a quality report.

## Technical Context

**Language/Version**: Python 3.12 (existing `adlc` package, uv, mypy strict, ruff)

**Primary Dependencies**:

- **Already used:** the feature 003–007 services, LiteLLM through the gateway, FastAPI, Typer,
  httpx, SQLAlchemy, Alembic.
- **New:** `mcp==1.30.0` (MIT, released 2026-09-07). It provides the server (`FastMCP`,
  streamable HTTP) and the client (research R-01).

**Storage**: migration 0008 adds two append-only tables, `run.knowledge_retrieval` and
`run.artifact_citation` (data-model.md). Knowledge documents are files in a folder
(`ADLC_KNOWLEDGE_DIR`; the demo set is in `data/knowledge/`).

**Testing**: pytest.

- **Unit (test first, constitution IX):**
  - scope resolution;
  - section splitting and BM25;
  - the data class filter;
  - citation and addressee validation;
  - the tools section of the request.
- **Integration:**
  - the knowledge server in-process with the real MCP client;
  - T0–T2 runs on the orchestration harness with `FakeTransport` recordings;
  - refusal and injection tests.
- **Scenario:** `adlc-replay --recording` over the reference set.
- **Live:** a `dev` profile replay.

**Target Platform**: Docker Compose. New `knowledge` service (same image, port 8020 internal,
health check). The orchestrator calls it.

**Project Type**: platform package (agents runtime) plus a small service.

**Performance Goals**:
- knowledge search under 200 ms for the demo set (hundreds of sections);
- each terminal reaches sign-off within 5 minutes live (SC-005).

**Constraints**:
- **No terminal-specific code** (constitution I).
- **Authorized calls:** every tool call is authorized first, and the server enforces scope and
  class again.
- **Untrusted content:** documents and tool output are data (constitution XI).
- **Spec versions are immutable:** content changes need new versions (research R-08).

**Scale/Scope**:
- 3 agents, 9 playbooks and 3 prompts;
- 6 knowledge sources, about 30 synthetic documents;
- 3 reference use cases.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| mcp 1.30.0 | Knowledge MCP server and the platform's MCP client (1.x keeps `httpx`; 2.x adds a new HTTP stack) | MIT |

### Demo moments supported (constitution XII)

| Moment | Supported by |
| --- | --- |
| D-1 Intake to design with real drafts | US1–US3 |
| D-6 Clarification instead of guessing | FR-017 (T0 asks the business owner) |
| D-7 Drift re-enters at T2 | A real T2 agent rebuilds the design |
| Agents are governed | US4 (scope refusals, injection resistance) |

**Post-MVP** (not built): subagents, vector search, real enterprise connectors, citations inside
the ledger record content (v3).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Agent behaviour comes from prompts, playbooks, specs and catalogues. Tool bindings and scopes come from the spec. The runtime changes are generic, and the scan covers new code | Pass |
| II Superset, not values | No use-case values in specs. Reference use cases are data files | Pass |
| III Agents build, humans decide | Agents only answer artifacts, citations, clarifications or tool requests; any status key fails validation. Sign-off is unchanged | Pass |
| IV Separation of duties | Every knowledge call passes `authorize` (`mcp:<source>:read` against `tool_scopes`). Scope and class are enforced again server-side. Refusals are logged | Pass |
| V Evidence-first | Retrievals and citations are append-only, and citations are bound to artifact versions. The ledger format is unchanged | Pass |
| VI Deterministic first | T0–T2 controls stay CEL and predicates. The reviewer scores only after blocking controls pass | Pass |
| VII Interfaces | The knowledge server is an MCP mock with the real tool shape. Agents use the `Tool` interface | Pass |
| VIII Open source | `mcp` (MIT), pinned at least two weeks old | Pass |
| IX Test first | Scope, search, filters and validation rules are written test-first | Pass |
| X Observable | `adlc.tool.call` spans and retrieval rows; run activity as before | Pass |
| XI Secure | Service token, read-only server, fail-closed data classes, data blocks and the injection tests | Pass |
| XII Simplicity | One server, keyword search, single agents, recordings for tests | Pass |
| XIII Naming | Tables, tools (`<source>_search`) and files follow Annex A | Pass |

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/008-terminal-agents-t0-t2/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── knowledge-mcp.md   # endpoints, tools, arguments, results, errors
│   ├── agent-output.md    # tools section, citations, addressee
│   └── replay.md          # adlc-replay
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/adlc/knowledge/                 # the knowledge MCP server (own process)
├── __init__.py  README.md  __main__.py   # adlc-knowledge entry point
├── documents.py   # load folder, front matter, sections, hashes
├── search.py      # BM25 over sections
├── scope.py       # grounding items → path prefixes / collections; data class filter
└── server.py      # FastMCP per source, token check, /health
src/adlc/agents/
├── tools.py       # Tool.call(arguments, context); KnowledgeTool (MCP client); describe()
├── context.py     # tools section; output instruction with citations
├── output.py      # citations and addressee validation
├── citations.py   # record retrievals and citations (SQL)
├── replay.py      # adlc-replay (Typer)
└── wiring.py      # build knowledge tools from bindings and settings
src/adlc/inbox/service.py           # run detail: citations
src/adlc/ui/pages/run.py            # Citations section (plain text)
src/adlc/config/settings.py         # KnowledgeSettings (server), knowledge URL and token (runtime)
db/migrations/versions/0008_terminal_agents.py
adlc-specs/shared/agents.yaml       # 1.1.0
adlc-specs/prompts/t0-intake-agent.md  t1-requirements-agent.md  t2-architect-agent.md
adlc-specs/playbooks/*.md           # nine playbooks at 1.1.0
adlc-specs/terminals/T0.yaml T1.yaml T2.yaml   # 1.1.0 (playbook refs)
data/knowledge/<source>/...         # synthetic enterprise knowledge set
data/reference_usecases/*.yaml      # three reference use cases
deploy/compose.yaml                 # knowledge service; orchestrator settings
tests/unit/knowledge/  tests/unit/agents/  tests/integration/knowledge/  tests/integration/agents/
tests/fixtures/replays/  tests/fixtures/knowledge/   # recordings; injection and over-class documents
tests/scenario/test_reference_replay.py
```

**Structure Decision**:
- **`knowledge/`** is a separate server module with its own entry point and container. It
  imports no orchestration code.
- **Agent changes** stay in `agents/` and are generic.
- **Content** lives in `adlc-specs/` and `data/`.

## Complexity Tracking

No constitution violations; nothing to justify.
