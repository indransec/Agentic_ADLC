# Implementation Plan: MCP Servers

**Branch**: `010-mcp-servers` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-mcp-servers/spec.md`

## Summary

Every MCP server the T3–T9 specs name, plus a pilot environment server, in two new processes
built like feature 008's knowledge server (research R-01):

- **`adlc-pilot-bridge`** (the only service on both the platform and pilot networks; no database
  credentials): pilot environments, Git, CI, artifact store, prompt registry, datasets, evaluation
  harness, red-team suite, personal-data scan, deploy, traffic, kill switch, observability,
  monitors and feedback. It wraps the pilot's own operations (feature 009) and three small pilot
  additions (`pilot-lab` for builds and datasets, a kill switch, feedback).
- **`adlc-tools`** (platform network, platform database): eval store and the enterprise mocks
  (ITSM, CMDB, agent registry, IAM, GRC, control library).

**Access**: the platform's tool gate authorises each call against the terminal's tool scopes
(feature 004), then signs a five-minute run token (HMAC) with the run's scopes and bound values
(branch, authorised hash, candidate hash, environment); the server checks the token again and uses
only the bound values (R-02, R-03).

**Records**: every call in `tools.tool_call`; evidence results (CI, harness, red-team, scan,
deploy, traffic, kill switch) in `tools.tool_result`, written by the platform; mock records in
`tools.enterprise_record`; all append-only (R-04).

**Evidence**: `env.dev`, `env.test`, `env.prod` and `template.version` come from the pilot through
the bridge, so T3's and T7's prerequisites and controls read real evidence (R-12).

**Specs**: MCP registry 2.0.0 (`host` per server, new `pilot_env`); T3, T4 and T5 2.0.0 with the
new scopes (R-13). Agents stay stubs until 011 and 012.

## Technical Context

**Language/Version**: Python 3.12, uv, ruff, mypy strict, pytest (platform); the pilot project for
its additions.

**Primary Dependencies**: MCP SDK 1.30.0 (already pinned, server and client), Starlette and
uvicorn (via MCP), httpx, SQLAlchemy and Alembic, ruamel.yaml, OpenTelemetry. **No new Python
dependencies.** The `git` binary is added to the platform image (Debian package, GPL-2.0; used as
a separate program, not linked).

**Storage**: migration `0009` (schema `tools`, three append-only tables); bridge volume
`bridge-data` (Git repositories, JSON Lines records, prompt and note texts).

**Testing**:
- **Unit (test first, constitution IX):** run tokens; argument filtering and bound values; harness
  metrics; red-team checks; masking; monitor evaluation; Git rules; evidence mapping.
- **Integration:** both servers through the real MCP client, the tool gate and testcontainers
  Postgres; the bridge against fake pilot endpoints that follow 009's contract and this feature's
  pilot additions (the platform never imports pilot code).
- **Pilot suite:** `pilot-lab`, kill switch, feedback.
- **Static:** network membership (only `pilot-bridge` and `jaeger` on both), no ports, no Docker
  socket, the bridge has no database or model settings, the server boundary (servers import no
  orchestration, ledger or API code).
- **Live:** the quickstart with `adlc-tools-probe`.

**Target Platform**: Docker Compose. New services `tools` (port 8030), `pilot-bridge` (8040) and
`pilot-lab` (8300, pilot image). No published ports.

**Settings** (environment only):
- shared: `ADLC_TOOLS_TOKEN_KEY` (secret, ≥ 32 characters);
- platform side: `ADLC_TOOLS_URL`, `ADLC_PILOT_BRIDGE_URL`, `ADLC_TOOLS_TIMEOUT_S`;
- tools server: database settings, `ADLC_TOOLS_PORT`;
- bridge: `ADLC_BRIDGE_PORT`, `ADLC_BRIDGE_DATA_DIR`, `ADLC_BRIDGE_PILOT_URLS` (dev, test,
  prod-sim, lab, traffic), `ADLC_BRIDGE_JAEGER_URL`, `ADLC_BRIDGE_MONITOR_INTERVAL_S`.

**Performance Goals**: tool calls under 2 s except CI (≤ 90 s), harness on 200 rows (≤ 60 s) and
red-team (≤ 60 s); SC-003 (fill to running dev package ≤ 5 minutes).

**Constraints**: no model-chosen run binding; no Docker socket; no external Git host; no LLM judge;
no incident text in telemetry; servers never hold model keys.

**Scale/Scope**: 22 servers (15 on the bridge, 7 on tools), about 45 tools; 3 datasets; one
red-team suite.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| `git` (Debian package in the platform image) | Bridge source control (R-05) | GPL-2.0, run as a program |

Not used: DeepEval, garak, PyRIT (clarification 2026-11-12); Docker SDK and Traefik (009 R-03);
GitPython; PyJWT.

### Demo moments supported (constitution XII)

| Moment | Supported by |
| --- | --- |
| D-3 rework routed to T3 after T4 finds a defect | Harness metrics by package (US3) |
| D-5 exception with waiver at T5 | Red-team and personal-data scan results (US3) |
| D-6 what T4 tested is what T7 deployed | Bound hashes: candidate in test, only the T6 hash deployable (US1, US4) |
| D-7 T8 drift event | Observability and the routing-accuracy monitor (US5) |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Servers, scopes and hosts come from the MCP registry; tool scopes from terminal specs; no terminal or use-case names in code | Pass |
| II Superset, not values | Datasets in the pilot, red-team attacks and controls in data files, monitor thresholds set by agents per use case | Pass |
| III Agents build, humans decide | Tools act on systems but never set outcomes; the kill switch is released only by a person | Pass |
| IV Separation of duties | Scopes per terminal checked twice; bound values stop an agent choosing hash, branch or environment | Pass |
| V Evidence-first | Every call recorded; evidence results written by the platform, hashed, append-only | Pass |
| VI Deterministic first | Harness, red-team, scan, CI and provisioning are deterministic; no LLM judge | Pass |
| VII Interfaces | Each mock implements the tool names a real server would; host URLs are settings | Pass |
| VIII Open source | No new Python dependencies; `git` as a program | Pass |
| IX Test first | Tokens, binding, metrics, checks and Git rules written test-first | Pass |
| X Observable | Every call traced with run id and outcome; telemetry masked | Pass |
| XI Secure | Run tokens, deny by default, only the bridge on both networks, no DB or model keys on the bridge, no Docker socket, output labelled as data | Pass |
| XII Simplicity | Two processes instead of 22; mocks as one record table; Git as a subprocess | Pass |
| XIII Naming | Servers, scopes and tools per Annex A (`mcp:<server>:<scope>`, `<server>_<tool>`) | Pass |

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/010-mcp-servers/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/ tools-mcp.md  run-token.md  pilot-additions.md
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
src/adlc/tools/                      # the two servers (no orchestration, ledger, policy or API imports)
├── token.py                         # run token sign/verify (shared with the platform side)
├── mcp_app.py                       # FastMCP endpoints per server, token middleware, health
├── registry.py                      # servers and scopes from mcp_servers.yaml, by host
├── bridge/                          # adlc-pilot-bridge
│   ├── pilot.py                     # HTTP client for the pilot hosts, lab and traffic
│   ├── environments.py  release.py  # pilot_env; cd, traffic_manager, kill_switch
│   ├── git_repo.py  ci.py  stores.py  # git, ci, artifact_store, prompt_registry
│   ├── evaluation.py  redteam.py  dlp.py  # dataset_registry, harness, redteam_harness, dlp_scanner
│   ├── telemetry.py  monitors.py  feedback.py  # observability, monitoring, feedback
│   └── __main__.py
└── enterprise/                      # adlc-tools
    ├── records.py                   # tools.enterprise_record, eval_store reads
    ├── servers.py                   # servicenow, cmdb, agent_registry, iam, grc, control_library, eval_store
    └── __main__.py
src/adlc/agents/mcp_tools.py         # McpTool: bound values, token, call, records (R-14)
src/adlc/agents/tool_records.py      # tools.tool_call / tool_result writer
src/adlc/policy/pilot_evidence.py    # env.* and template.version through the bridge (R-12)
src/adlc/tools/probe.py              # adlc-tools-probe (dev command)
db/migrations/versions/0009_mcp_tools.py
data/redteam/suite.yaml  data/controls/controls.yaml
adlc-specs/shared/mcp_servers.yaml   adlc-specs/schema/catalogues/mcp_servers.schema.json
adlc-specs/terminals/T3.yaml T4.yaml T5.yaml
pilot/src/pilot_tools/lab.py         # pilot-lab: build, packages, datasets
pilot/src/pilot_tools/host.py        # + POST /kill
pilot/src/pilot_tools/traffic.py     # + GET /feedback
pilot/datasets.yaml
deploy/compose.yaml  deploy/api.Dockerfile (git)  .env.example
tests/unit/tools/  tests/integration/tools/  tests/unit/test_pilot_boundary.py
```

**Structure Decision**: one new package `adlc.tools` with two entry points (`adlc-tools`,
`adlc-pilot-bridge`), sharing token and MCP plumbing; the platform-side client lives with the
agents runtime, next to 008's knowledge tool.

## Complexity Tracking

| Choice | Why | Simpler alternative rejected because |
| --- | --- | --- |
| Two server processes | Only the bridge crosses networks, and it holds no database role | One process would put database credentials on the pilot network |
| Signed run tokens | Server-side check per run and scope (SC-001) | A shared bearer token cannot tell one run or scope from another |
| A new pilot service (`pilot-lab`) | Builds and datasets need pilot code; the platform never imports it | Building in the bridge would import the pilot or duplicate it |
