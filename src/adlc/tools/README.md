# adlc.tools

The MCP tool servers of the acting terminals (feature 010; SA §11, §13). Specification:
`specs/010-mcp-servers/`; contracts: `contracts/tools-mcp.md`, `contracts/run-token.md`,
`contracts/pilot-additions.md`.

## Processes

| Process (service) | Networks | Holds | Servers (registry `host`) |
| --- | --- | --- | --- |
| `adlc-pilot-bridge` (`pilot-bridge`) | platform and pilot | Volume `bridge-data`; no database, model, knowledge or session settings | `bridge`: pilot_env, git, ci, artifact_store, prompt_registry, dataset_registry, harness, redteam_harness, dlp_scanner, cd, traffic_manager, kill_switch, observability, monitoring, feedback |
| `adlc-tools` (`tools`) | platform | App database role | `tools`: eval_store, servicenow, cmdb, agent_registry, iam, grc, control_library |

Which process serves a server is the `host` field of `adlc-specs/shared/mcp_servers.yaml`; host
URLs are settings. The knowledge server (feature 008) stays its own process.

## Modules

| Module | Purpose |
| --- | --- |
| `catalogue.py` | Every tool: server, name, scope, the arguments the model may set, bound values, evidence kind, time limit. Read by both sides; `tests/unit/tools/test_contract.py` keeps it equal to the contract. |
| `registry.py` | Servers, scopes, hosts and bound-value references from the MCP registry; start-up checks. |
| `token.py` | Run tokens: HMAC-SHA256 over canonical JSON, five minutes, scopes and bound values. |
| `mcp_app.py` | One MCP endpoint per server (low-level SDK server, streamable HTTP, stateless, JSON); the token is verified for the tool's scope and bound values before a handler runs; per-tool time limits; token-checked resources; audit hook; `/health`. |
| `client.py` | The platform's MCP client with a per-call token. |
| `bridge/` | `pilot.py` (HTTP client of the pilot), `environments.py`, `git_repo.py`, `stores.py` (CI, artifact store, prompt registry), `evaluation.py` (datasets, harness, red-team, personal-data scan), `release.py` (deploy, traffic, kill switch), `operate.py` (observability, monitors, feedback), `records.py` (JSON Lines), `app.py`. |
| `enterprise/` | `records.py` (`tools.enterprise_record`, eval store reads), `servers.py` (the mocks), `app.py`. |
| `probe.py` | `adlc-tools-probe`: call a tool as a terminal through the real gate, token and records (dev and demo). |

The platform side lives with the agents runtime: `adlc/agents/mcp_tools.py` (`McpTool`, bound
values, records) and `adlc/agents/tool_records.py`; the pilot evidence source is
`adlc/policy/pilot_evidence.py`.

## Rules

- **Checked twice.** The tool gate authorises the call against the terminal's tool scopes
  (feature 004); then the server verifies the run token for the tool's scope.
- **Bound values.** Branch (`uc/<run id>`), environment (the one environment scope the terminal
  holds), candidate hash and authorised hash come from the run and real ledger evidence through the
  registry's `bound_values`; synthetic or ambiguous evidence binds nothing and the call is refused.
- **Records.** Every call, including gate refusals, in `tools.tool_call`; evidence results in
  `tools.tool_result`; mock records in `tools.enterprise_record`. All append-only.
- **No incident text** leaves the pilot through tools: labels stay with the harness, traces keep an
  attribute allowlist, findings are masked.
- **Imports.** Servers import nothing from orchestration, ledger, policy, agents, API, inbox, UI or
  knowledge; the bridge imports no database or model code (`tests/unit/tools/test_boundary.py`).
