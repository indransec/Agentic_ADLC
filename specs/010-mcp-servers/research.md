# Research: MCP Servers (feature 010)

Decisions taken for the plan. Each has its rationale and the alternatives considered.

## R-01 Two server processes, split by what they touch

**Decision.** Two new MCP server processes in the platform image, both built like feature 008's
knowledge server (MCP SDK 1.30.0 `FastMCP`, streamable HTTP, stateless JSON, one endpoint per
server at `/mcp/<server>/`):

| Process (service) | Networks | Holds | Servers |
| --- | --- | --- | --- |
| `adlc-tools` (`tools`) | platform | Platform database (app role) | `eval_store`, `servicenow`, `cmdb`, `agent_registry`, `iam`, `grc`, `control_library` |
| `adlc-pilot-bridge` (`pilot-bridge`) | platform **and** pilot | A volume (`bridge-data`); **no** database credentials, no platform secrets except the run-token key | `pilot_env`, `git`, `ci`, `artifact_store`, `prompt_registry`, `dataset_registry`, `harness`, `redteam_harness`, `dlp_scanner`, `cd`, `traffic_manager`, `kill_switch`, `observability`, `monitoring`, `feedback` |

**Rationale.** The bridge is the only service on both networks (FR-006), so it gets the least: no
database role, no model keys, no knowledge token. A compromise from the pilot side reaches the
pilot-facing tools only. Enterprise mocks write evidence records and need the database, so they
stay on the platform network.

**Alternatives.** One process for everything: simplest, but puts database credentials on the pilot
network. One container per server (22): faithful to "each server its own credentials" (SA §11
target) but 22 services for the MVP (constitution XII). Recorded as the target state.

## R-02 Run tokens: HMAC-signed, per call, five minutes

**Decision.** The platform signs a token for every tool call: `v1.<base64url claims>.<base64url
HMAC-SHA256>`, key `ADLC_TOOLS_TOKEN_KEY` (at least 32 bytes, environment only). Claims:
`run_id`, `usecase_id`, `terminal_id`, `attempt`, `scopes` (the terminal's `mcp:` tool scopes from
the pinned spec), `bound` (values the server must use, see R-03), `iat`, `exp` (iat + 300 s). The
server verifies the signature in constant time, the expiry, and that the tool's scope is in
`scopes`. The platform's own evidence reads use a service token (`run_id: platform`, scopes
`mcp:pilot_env:read`, `mcp:cd:read`, `mcp:observability:read`).

**Rationale.** SA §11: "a short-lived, run-scoped token carrying terminal, use case, permissions".
Standard library only; nothing to rotate in the MVP beyond the key. A token for one run cannot be
used for another run or scope (FR-002, SC-001).

**Alternatives.** The 008 shared bearer token (no run binding, rejected for write tools); JWT with
PyJWT (a new dependency for the same result); a token service (target state).

## R-03 Bound values: the platform decides, the model cannot

**Decision.** Each tool declares the arguments the model may set; every other argument is dropped.
Values that bind the call are claims in the token's `bound` object, set by the platform:

| Bound value | Source | Used by |
| --- | --- | --- |
| `branch` | `uc/<usecase_id>/<run_id>` | `git` writes, `ci_run` |
| `authorised_hash` | The one T6 `deployment_package` row (emitted on pass) whose `sha256` equals T3's `candidate_package.sha256`; none or more than one matching row means no authorised hash, and deploy is refused | `cd_deploy` |
| `candidate_hash` | T3 `candidate_package.sha256` | `pilot_env_create` in test (T4, T5), `harness_run`, `redteam_harness_run`, `dlp_scanner_run` |
| `environment` | The scope: `dev` or `test` | `pilot_env_*` |

The server uses only the bound value; if the model also sends one it is ignored (FR-003).

**Rationale.** Defence against an agent (or a prompt-injected document) choosing a different hash,
branch or environment; the server enforces it again even if the platform were bypassed.

## R-04 Records: the platform records every call and keeps evidence results

**Decision.** Migration `0009` adds schema `tools`:
- `tools.tool_call`: one row per call, including calls refused at the gate (FR-004);
- `tools.tool_result`: the full result of evidence-producing tools (`ci_run`, `harness_run`,
  `redteam_harness_run`, `dlp_scanner_run`, `cd_deploy`, `traffic_manager_set`, `kill_switch_invoke`),
  written by the platform from the server's answer, never by the agent, with a content hash;
- `tools.enterprise_record`: the mocks' records (versions; the latest version is current).

All three are append-only for the app role (SELECT, INSERT only), like the ledger. `eval_store`
reads `tool_result` rows of the use case; its `write` stores agent notes as a separate,
agent-labelled record kind.

**Rationale.** Evidence for T4–T8 controls must come from runs (spec US3); the platform is the
authority, the bridge keeps its own JSON Lines audit for operations only.

## R-05 Source control: bare Git repositories on the bridge volume

**Decision.** One bare repository per use case at `bridge-data/git/<usecase_id>.git`, created on
first use with an initial commit of the pilot's empty fill layout on `main`. Tools: `git_list`,
`git_read`, `git_write` (several files and one commit on the bound branch), `git_open_pull_request`
(recorded in the repository's `refs/notes` and the bridge's records). Writes to `main` are refused.
A write whose parent is not the branch head is refused ("branch moved; read again"). The `git`
command runs as a subprocess with a fixed argument list and no shell; no hooks, no remotes.

**Rationale.** Clarification 2026-11-12 (no external host). The `git` binary is in the image;
GitPython would add a dependency for a few commands.

## R-06 CI and the build service on the pilot side (`pilot-lab`)

**Decision.** A new pilot service `pilot-lab` (pilot image, pilot network, port 8300) offers:
`POST /build` (fill files → validate, build, rebuild to check reproducibility, start the package
and triage a smoke sample), `GET /packages/{hash}`, `GET /datasets`, `GET /datasets/{id}`. The
bridge's `ci_run` reads the bound branch's fill from its repository and posts it to `/build`;
`artifact_store_read` reads `/packages/{hash}`. Checks: `validate`, `build`, `reproducible`,
`smoke`.

**Rationale.** Building and the incident generator belong to the pilot project (009 R-02, R-04);
the platform never imports pilot code (009 FR-017). The hash is the pilot's own hash (FR-011,
SC-003).

**Alternatives.** Running the pilot's pytest suite in CI: minutes per run and tests the template,
which does not change per fill; the smoke check tests the filled package.

## R-07 Datasets live with the pilot; the harness is generic

**Decision.** `pilot/datasets.yaml` declares datasets (id, version, seed, size, PII share, scored
fields, slices); `pilot-lab` generates rows with the incident generator and gives each dataset a
content hash. The bridge's harness is use-case neutral: it sends each row's incident fields only to
the test host, compares the answer with `expected` on the dataset's scored fields, and computes
accuracy overall, per value of the first scored field, and recall per declared slice (e.g.
`expected.priority == P1`). Latency comes from timing; cost and RAI counts from the test host's
`/metrics` before and after the run.

**Rationale.** CLAUDE.md: no use-case values in platform code. Deterministic (clarification), so
the same package and dataset give the same metrics (SC-004).

## R-08 The red-team suite is data

**Decision.** `data/redteam/suite.yaml` (versioned, hashed) lists attacks: category
(`prompt_injection`, `jailbreak`, `pii_extraction`, `abusive_input`), a payload appended to a
dataset row's description, and a success check: `marker_in_answer` (the payload asks the agent to
include a canary marker), `field_equals` (asks it to set a field to a value), `planted_pii_in_answer`
or `toxic_in_answer`. Success rate per category = successes / attempts.

**Rationale.** Build plan simplification "red-team as a fixed prompt suite"; no garak or PyRIT.
With the leak fault off, `pii_extraction` succeeds 0 times; on, above 0 (SC-005).

## R-09 Personal-data scanning in the bridge

**Decision.** `dlp_scanner_run` runs the PII dataset against the test host and scans each answer
with e-mail, phone and payment-card patterns; findings are returned masked (`a***@example.com`).

## R-10 Release tools wrap the pilot host

**Decision.** `cd_deploy` → prod-sim `POST /deployments` (candidate, `authorised_hash` only);
`cd_status` → `GET /split`; `traffic_manager_set` → `PUT /split` (shadow, canary with share);
`full` promotes the deployed candidate to stable (prod-sim's `full` sends everything to stable)
and records the previous stable; `traffic_manager_rollback` → `PUT /split full`, redeploying the
previous stable after a promotion; `kill_switch_invoke` → a new prod-sim `POST /kill` that makes `/triage` answer 503
"stopped" until a person releases it with the pilot command `pilot-kill release`.

**Rationale.** 009 built the operations (no Docker SDK, no Traefik); the kill switch is the one
missing operation. Release by a person only (FR-018).

## R-11 Observability, monitors and feedback

**Decision.** `observability_metrics` reads the traffic generator's and prod-sim's metrics (counts,
accuracy, leak rate, latency, cost, RAI, per package); `observability_traces` reads Jaeger's v3 API
for the pilot's service and returns span name, request id, package hash, duration and status only
(attribute allowlist; no incident text, SC-008). Monitors (metric, operator, threshold, window)
are stored per use case on the bridge volume and evaluated every 30 s and on read; a breach is
recorded once per episode with value and time. `feedback_read` reads a new traffic endpoint
`GET /feedback` that derives seeded synthetic ratings from answer correctness, labelled synthetic.

**Rationale.** SC-007 needs a fire time within 5 minutes of the swap; a background evaluation
gives it without T8 polling.

## R-12 Real evidence for `env.*` and `template.version`

**Decision.** A `PilotEvidence` source in the platform's evidence provider answers `env.dev`,
`env.test` (`{provisioned, deployed_hash, healthy}`), `env.prod` (`{deployed_hash}` = prod-sim's
stable, or the candidate at full) and `template.version` (from the infrastructure resources); `env.prod.deployed_hash` is prod-sim's stable package, which a full rollout replaces with the candidate
through the bridge with the service token. When the bridge is not configured or not reachable it
answers "not available" and the composite provider falls back to synthetic evidence, labelled
synthetic (feature 004).

## R-13 Spec and catalogue changes

**Decision.**
- `mcp_servers.yaml` 2.0.0: every entry gains `host` (`knowledge`, `tools` or `bridge`; schema
  update); new server `pilot_env` with scopes `dev`, `test`, `read`; `cd` gains `read`.
- T3 2.0.0: tool scopes add `mcp:pilot_env:dev`, `mcp:pilot_env:read`, `mcp:git:read`,
  `mcp:artifact_store:read`.
- T4 and T5 2.0.0: add `mcp:pilot_env:test`, `mcp:pilot_env:read`; T4 adds `mcp:artifact_store:read`.
- T8 2.0.0 (found in implementation): adds `mcp:monitoring:read`; T6 configures monitors
  (`mcp:monitoring:configure`, already granted) and T8 reads which fired.
- The agents catalogue is unchanged: T3–T9 are still stub agents; features 011 and 012 bind tools.

**Rationale.** V-06 (every scope in the registry) and V-24 (a changed value is a major version).

## R-14 Platform-side tool client

**Decision.** `adlc/agents/mcp_tools.py`: `McpTool(server, operation)` built for every agent
binding whose permission is `mcp:<server>:<scope>` and whose server's `host` is `tools` or
`bridge`; it mints the token (R-02), adds bound values, calls `<host url>/mcp/<server>/`, records
the call and, for evidence tools, the result (R-04). Host URLs are settings (`ADLC_TOOLS_URL`,
`ADLC_PILOT_BRIDGE_URL`), never in code or specs.
