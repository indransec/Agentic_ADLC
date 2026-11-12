# Tasks: MCP Servers

**Input**: Design documents from `specs/010-mcp-servers/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Test-first for:

- run tokens (sign, verify, expiry, scope, tampering);
- argument filtering and bound values;
- Git rules;
- harness metrics, red-team checks and masking;
- monitor evaluation;
- the boundary and network tests.

**Organization**: setup and foundation, then one phase per user story (US1–US4 P1, US5–US6 P2),
then polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US6)

## Conventions used by every task

- **Servers:** `src/adlc/tools/` imports nothing from `adlc.orchestration`, `adlc.ledger`,
  `adlc.policy`, `adlc.agents`, `adlc.api` or `adlc.inbox`. The bridge never imports pilot code; it
  speaks to the pilot over HTTP.
- **Platform tests of the bridge** use fake pilot endpoints that follow 009's contract and
  `contracts/pilot-additions.md`; the pilot's own suite tests the pilot additions.
- **No names in code:** no terminal ids, use-case values, server lists or host URLs in code; they
  come from specs, catalogues, data files and settings.
- **Records:** every call ends in `tools.tool_call`; evidence results in `tools.tool_result`.

---

## Phase 1: Setup

- [X] T001 Settings in `src/adlc/config/settings.py` (and their validation messages):
  - shared: `ADLC_TOOLS_TOKEN_KEY` (secret, at least 32 characters);
  - platform side: `ADLC_TOOLS_URL`, `ADLC_PILOT_BRIDGE_URL`, `ADLC_TOOLS_TIMEOUT_S` (default 30);
  - `ToolsSettings` (database settings, `ADLC_TOOLS_PORT` 8030, allowed hosts);
  - `BridgeSettings` (`ADLC_BRIDGE_PORT` 8040, `ADLC_BRIDGE_DATA_DIR`, `ADLC_BRIDGE_PILOT_DEV_URL`, `_TEST_URL`, `_PRODSIM_URL`, `_LAB_URL`, `_TRAFFIC_URL`, `ADLC_BRIDGE_JAEGER_URL`, `ADLC_BRIDGE_MONITOR_INTERVAL_S` 30, allowed hosts) with **no** database or model fields.

  Add the keys to `.env.example` (key `REPLACE_ME`) and keep `tests/unit/test_env_example.py` passing.
- [X] T002 [P] Package skeleton `src/adlc/tools/{__init__,token,mcp_app,registry}.py`, `bridge/`, `enterprise/`; entry points `adlc-tools`, `adlc-pilot-bridge`, `adlc-tools-probe` in `pyproject.toml`; `src/adlc/tools/README.md` stub.
- [X] T003 [P] Migration `db/migrations/versions/0009_mcp_tools.py`: schema `tools`; tables `tool_call`, `tool_result`, `enterprise_record` exactly as data-model.md (unique `system, record_id, version`); SELECT and INSERT only for the app role; downgrade drops the schema. Migration test in `tests/integration/db/` (upgrade, downgrade, an UPDATE and a DELETE refused for the app role).
- [X] T004 [P] `deploy/api.Dockerfile`: install the `git` Debian package (no recommends); `git --version` in the image smoke test.
- [X] T005 [P] Boundary tests written first:
  - `tests/unit/tools/test_boundary.py`: the import rules above;
  - `tests/unit/test_pilot_boundary.py` updated: only `pilot-bridge` and `jaeger` on both networks; `tools` on `platform` only; `pilot-lab` on `pilot` only; no published ports; no Docker socket; the `pilot-bridge` service has no `ADLC_DB_*`, model key or knowledge token variables.

**Checkpoint**: `make check` passes with the skeleton (the new boundary tests fail until Compose changes in US1/US6, so mark them `xfail(strict=True)` until then).

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T006 [P] `tests/unit/tools/test_token.py`: round trip; tampered claims or signature; wrong key; expired; `iat` more than 60 s ahead; scope not granted; bound value missing where a tool requires it; canonical JSON (key order does not change the signature); the token never appears in error text.
- [X] T007 [P] `tests/unit/tools/test_registry.py`: servers and scopes by host from `mcp_servers.yaml`; an unknown server or scope is refused; every tool a server declares has a scope in the registry.
- [X] T008 [P] `tests/unit/agents/test_mcp_tools.py`: only declared model arguments pass; bound values come from the run (branch `uc/<usecase>/<run>`, candidate hash from T3's `candidate_package.sha256`, authorised hash = the one T6 `deployment_package` row whose `sha256` equals the candidate hash — none or several matching rows give no authorised hash, environment from the scope); a model-sent bound value is dropped; output is capped and wrapped as data; a tool with no host URL setting is unavailable, not called.

### Implementation

- [X] T009 `src/adlc/tools/token.py` (contracts/run-token.md): `sign(claims, key)`, `verify(token, key, scope, now)` with the checks in order; `TokenError(reason)`.
- [X] T010 Spec catalogue changes (research R-13):
  - `adlc-specs/shared/mcp_servers.yaml` 2.0.0 with `host` on every entry, new `pilot_env` (`dev`, `test`, `read`), `cd` adds `read`;
  - `adlc-specs/schema/catalogues/mcp_servers.schema.json` (`host` required, enum `knowledge`, `tools`, `bridge`);
  - T3 2.0.0 (adds `mcp:pilot_env:dev`, `mcp:pilot_env:read`, `mcp:git:read`, `mcp:artifact_store:read`), T4 2.0.0 (`mcp:pilot_env:test`, `mcp:pilot_env:read`, `mcp:artifact_store:read`), T5 2.0.0 (`mcp:pilot_env:test`, `mcp:pilot_env:read`);
  - `adlc-specs/CONVERSION.md` notes; `make spec-validate` passes; registration and version tests updated (V-24).
- [X] T011 `src/adlc/tools/registry.py` and `src/adlc/tools/mcp_app.py`: build one FastMCP endpoint per server of a host at `/mcp/<server>/` (stateless, JSON) from tool definitions (name, scope, model arguments, bound values, handler); a middleware that verifies the run token for the tool's scope before the handler runs and puts the claims in the request context; per-tool time limits enforced by the server (CI 90 s, harness and red-team 60 s, others 10 s; `timed out` error); `/health`; DNS-rebinding protection; output size caps; logs with counts only. Contract test `tests/unit/tools/test_contract.py`: the tools each server declares equal `contracts/tools-mcp.md` (names, scopes, model arguments, bound values) (FR-007).
- [X] T012 `src/adlc/agents/tool_records.py` (writer for `tools.tool_call` and `tools.tool_result`, canonical-JSON hashes) and `src/adlc/agents/mcp_tools.py` (`McpTool`, `mcp_tools(agents, registry, settings, …)`): mint the token after the gate allowed the call, add bound values, call through the MCP client (reuse 008's caller pattern with a per-call token), record the call (and the result for evidence tools), map failures to `failed`, `timed_out`, `unavailable`. Record calls refused by `ToolGate` too (`src/adlc/agents/tools.py` hook). Wire into the agents' tool set in `src/adlc/agents/wiring.py`.

**Checkpoint**: tokens, registry and the client pass their tests; specs validate.

---

## Phase 3: User Story 1 – Pilot environments through scoped tools (P1)

**Goal**: T3 provisions dev, T4/T5 provision test, infrastructure definitions are readable, and T3's prerequisites read real evidence.

**Independent Test**: as T3 and T4 runs, create, read and tear down environments through the gate and the MCP client; check refusals at the gate and at the server, and the records.

- [X] T013 [P] [US1] Tests `tests/unit/tools/test_environments.py` (fake pilot): create in dev with a model-chosen hash, create in test with the bound candidate hash only, status, delete, infra resources and the `pilot_env_infra` tool; a host that is down gives `unavailable`.
- [X] T014 [P] [US1] Integration tests `tests/integration/tools/test_bridge_environments.py`: through `ToolGate` and the real MCP client against the bridge app (fake pilot): T3 creating test is refused at the gate (record with reason, nothing reaches the fake pilot); a direct call without a token, with an expired one or with a T3 token for test is refused by the server; records in `tools.tool_call` and `tools.tool_result`.
- [X] T015 [US1] `src/adlc/tools/bridge/pilot.py` (HTTP client for the pilot hosts, lab and traffic, timeouts, `unavailable`) and `src/adlc/tools/bridge/environments.py` (`pilot_env` tools and `infra://<environment>` resources).
- [X] T016 [US1] `src/adlc/policy/pilot_evidence.py`: `env.dev`, `env.test`, `env.prod`, `template.version` through the bridge with the service token (research R-12), wired into the composite evidence provider ahead of synthetic; tests that PRE-T3-03 and PRE-T3-04 decisions are not labelled synthetic when the bridge answers, and fall back (labelled) when it does not.
- [X] T017 [US1] `src/adlc/tools/bridge/__main__.py` (`adlc-pilot-bridge`: validate settings, serve) and Compose service `pilot-bridge` (platform image, networks `platform` and `pilot`, volume `bridge-data`, health check, no ports); platform services get `ADLC_PILOT_BRIDGE_URL` and `ADLC_TOOLS_TOKEN_KEY`; remove the boundary `xfail`s that this satisfies.

**Checkpoint**: US1 passes alone.

---

## Phase 4: User Story 2 – Build: source control, CI and the artifact store (P1)

**Goal**: a fill on a branch becomes a package hash with CI checks, the same as the pilot's own build.

**Independent Test**: as a T3 run, write the default fill, run CI, read the manifest; compare with `pilot-build`.

- [X] T018 [P] [US2] Pilot tests `pilot/tests/unit/test_lab.py` and `pilot/tests/integration/test_lab.py`: `POST /build` with the default fill returns the four checks passed and the hash `pilot-build` gives; an invalid fill fails `validate` naming the part; `GET /packages/{hash}`; `GET /datasets` and `/datasets/{id}` reproducible with content hashes; unknown dataset 404.
- [X] T019 [US2] `pilot/datasets.yaml` (golden, regression, pii with scored fields `team`, `category`, `priority` and slice `p1: priority == P1`), `pilot/src/pilot_tools/lab.py` (`pilot-lab`, port 8300) and Compose service `pilot-lab` (pilot image, pilot network, `pilot-packages` volume).
- [X] T020 [P] [US2] Tests `tests/unit/tools/test_git_repo.py`: repository created per use case with the fill layout on `main`; writes only on the bound branch; `main` refused; paths outside the fill layout refused; size limits; a write with a stale `parent` refused; pull request recorded; no hooks run (a planted hook does nothing).
- [X] T021 [US2] `src/adlc/tools/bridge/git_repo.py`: bare repositories under `ADLC_BRIDGE_DATA_DIR/git`, `git` as a subprocess with a fixed argument list, `GIT_CONFIG_NOSYSTEM`, hooks path empty, no remotes; tools `git_list`, `git_read`, `git_write`, `git_open_pull_request`.
- [X] T022 [US2] `src/adlc/tools/bridge/ci.py` (`ci_run`: read the branch's fill, `POST /build`, return checks and hash) and `src/adlc/tools/bridge/stores.py` (`artifact_store_read`, `artifact_store_write`, `prompt_registry_write`, `prompt_registry_read`, content-addressed), with tests against the fake lab.

**Checkpoint**: US2 passes alone.

---

## Phase 5: User Story 3 – Evaluate and assure against the test environment (P1)

**Goal**: deterministic metrics, red-team rates and personal-data findings for the candidate in test, stored as evidence.

**Independent Test**: as a T4 run, run the harness twice; as a T5 run, run the red-team suite and the scan with and without the leak.

- [X] T023 [P] [US3] Tests `tests/unit/tools/test_evaluation.py`: metrics from fixed rows and answers (accuracy, accuracy by the first scored field, slice recall, latency p95, cost and RAI deltas from host metrics); the incident fields only are sent; an unregistered dataset is refused; the same inputs give the same metrics.
- [X] T024 [P] [US3] Tests `tests/unit/tools/test_redteam.py` and `test_dlp.py`: each check type (`marker_in_answer`, `field_equals`, `planted_pii_in_answer`, `toxic_in_answer`); rates per category; masking (`a***@example.com`, last two digits of phones, last four of cards).
- [X] T025 [US3] `src/adlc/tools/bridge/evaluation.py` (`dataset_registry_list`, `harness_run`) per research R-07.
- [X] T026 [US3] `data/redteam/suite.yaml` (version 1.0.0, at least 3 attacks per category) and `src/adlc/tools/bridge/redteam.py` (`redteam_harness_run`); `src/adlc/tools/bridge/dlp.py` (`dlp_scanner_run`).
- [X] T027 [US3] Integration `tests/integration/tools/test_bridge_evaluation.py` (fake test host with a degraded mode): harness results stored in `tools.tool_result` with the package hash; repeat runs identical (SC-004); the degraded package at least 20 points lower; red-team `pii_extraction` 0 without the leak and above 0 with it; the scan finds every planted value in leaked answers (SC-005).

**Checkpoint**: US3 passes alone.

---

## Phase 6: User Story 4 – Release: deploy, traffic and the kill switch (P1)

**Goal**: only the T6-authorised hash deploys; the split moves and rolls back; the kill switch stops the pilot until a person releases it.

**Independent Test**: as a T7 run, deploy the authorised hash and step through the split; try another hash; as a T8 run, invoke the kill switch.

- [X] T028 [P] [US4] Pilot tests `pilot/tests/integration/test_kill.py`: activate makes `/triage` answer 503; activating twice 409; release restores; records in `faults.jsonl`; `pilot-kill release` command.
- [X] T029 [US4] `pilot/src/pilot_tools/host.py` `POST /kill` and `pilot/src/pilot_tools/cli.py` `pilot-kill` (release by a person; the bridge only activates).
- [X] T030 [P] [US4] Tests `tests/unit/tools/test_release.py` and integration `tests/integration/tools/test_bridge_release.py`: `cd_deploy` with the bound authorised hash; no authorised hash refused at the platform (no T6 pass) and at the server (token without `authorised_hash`); a model-sent hash ignored; `traffic_manager_set` and `traffic_manager_rollback`; `kill_switch_invoke` twice; evidence results recorded (SC-006).
- [X] T031 [US4] `src/adlc/tools/bridge/release.py`: `cd_deploy`, `cd_status`, `traffic_manager_set`, `traffic_manager_rollback`, `kill_switch_invoke`.

**Checkpoint**: US4 passes alone.

---

## Phase 7: User Story 5 – Operate: telemetry, monitoring and feedback (P2)

**Goal**: T8 reads masked telemetry, sets monitors that fire on the model swap, and reads synthetic feedback.

**Independent Test**: with fake traffic metrics, set a monitor, lower the accuracy, check it fires and records the time.

- [ ] T032 [P] [US5] Pilot test and code: `pilot/src/pilot_tools/traffic.py` `GET /feedback` (seeded ratings from answer correctness, `synthetic: true`) with a test in `pilot/tests/integration/test_traffic.py`.
- [ ] T033 [P] [US5] Tests `tests/unit/tools/test_telemetry.py` and `test_monitors.py`: metrics per package; traces keep only allowlisted attributes (no description, title, reason or personal data); monitors per use case; operators; one fired event per breach episode with value and time; re-arms after recovery; background evaluation interval.
- [ ] T034 [US5] `src/adlc/tools/bridge/telemetry.py` (`observability_metrics`, `observability_traces` via Jaeger's v3 API), `monitors.py` (`monitoring_configure`, `monitoring_read`, background loop), `feedback.py` (`feedback_read`).

**Checkpoint**: US5 passes alone.

---

## Phase 8: User Story 6 – Enterprise records: ITSM, CMDB, registries, IAM and GRC mocks (P2)

**Goal**: T6–T9 tools create and read enterprise records kept in the platform.

**Independent Test**: create a change and an incident, register an agent, revoke scopes, file a report; read them back.

- [ ] T035 [P] [US6] Integration tests `tests/integration/tools/test_enterprise.py` (testcontainers Postgres, the `tools` app through the MCP client): ids `CHG-<n>`, `INC-<n>`, …; use case, run and terminal from the token; versions on update (`cmdb_write`, `agent_registry_write`); `iam_revoke` then `iam_read` shows it; `eval_store_read` returns the use case's harness, red-team and scan results only; `eval_store_write` notes labelled agent-authored; `control_library_read` by id and topic; a token for another use case sees nothing of this one.
- [ ] T036 [US6] `src/adlc/tools/enterprise/records.py`, `servers.py`, `data/controls/controls.yaml` (security, privacy and RAI controls named in the T5 checklist) and `src/adlc/tools/enterprise/__main__.py` (`adlc-tools`).
- [ ] T037 [US6] Compose service `tools` (platform image, platform network, database settings, health check, no ports); remove the remaining boundary `xfail`s.

**Checkpoint**: US6 passes alone.

---

## Phase 9: Polish

- [ ] T038 [P] `src/adlc/tools/probe.py` (`adlc-tools-probe`): call any tool as a named terminal for a use case through the real gate, token and records (a dev command; refuses to run when `ADLC_ENV` is not `dev` or `demo`).
- [ ] T039 [P] Documents: `src/adlc/tools/README.md` (servers, tools, tokens, records); SA §13 (integration table: MVP column for each server), §11 (run tokens), §15 (services); build plan row 010 (no Docker SDK or Traefik, no DeepEval or garak/PyRIT); `deploy/README.md` (services and settings).
- [ ] T040 Run the 001–009 suites, the new suites and the pilot suite 10 times in a row and record the result (SC-009).
- [ ] T041 Run `make check` and fix any failure.
- [ ] T042 Live check (quickstart §2): every server answers; fill to running dev package within 5 minutes with CI's hash equal to `pilot-build` (SC-003); out-of-scope calls refused at both ends (SC-001); a record per call (SC-002); harness repeatable and degraded ≥ 20 points lower (SC-004); red-team with and without the leak (SC-005); only the T6 hash deploys (SC-006); monitor fires within 5 minutes of the swap (SC-007); no incident text in telemetry or tool output over a traffic run (SC-008). Record the results.

---

## Dependencies and execution order

- **Phase 1** then **Phase 2** (tokens, registry, client, spec changes) block every story.
- **US1** first (it brings the bridge service up).
- **US2**, **US3** and **US4** need US1's bridge; US3 also needs US2's `pilot-lab` (datasets).
- **US5** needs US1; **US6** needs Phase 2 only.
- **Phase 9** comes last.

## Parallel opportunities

- T002–T005 together.
- T006–T008 together.
- Within stories, the test tasks marked [P] together; pilot tasks (T018, T028, T032) alongside platform tasks.
- US6 can run alongside US2–US5.

## Implementation strategy

1. **Foundation**: Phases 1–2.
2. **First crossing**: US1 (the bridge and real evidence).
3. **Build, evaluate, release**: US2–US4.
4. **Operate and records**: US5–US6.
5. **Polish**: Phase 9.

Run `make check` and commit at every checkpoint.
