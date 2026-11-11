# Tasks: Pilot Environments

**Input**: Design documents from `specs/009-pilot-environments/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required. Test-first for:

- fill validation and deterministic packaging;
- the simulated and degraded models;
- the PII check;
- incident generation;
- the splitter;
- the boundary and network-isolation tests.

**Organization**: setup and foundation, then one phase per user story (US1–US4 P1, US5–US6 P2),
then polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US6)

## Conventions used by every task

- **Location:** all pilot code is under `pilot/` (its own uv project). Nothing in `pilot/` imports
  `adlc`, and nothing in `src/adlc` imports the pilot.
- **Running pilot checks:** `uv run --project pilot ...`. The root `make check` runs them too.
- **Data:** synthetic only. Planted personal data appears only where a test asks for it.

---

## Phase 1: Setup

- [X] T001 Create the pilot project `pilot/pyproject.toml`:
  - Python 3.12;
  - dependencies: FastAPI, uvicorn, httpx, pydantic, ruamel.yaml and the OpenTelemetry SDK and OTLP exporter, at the platform's pinned versions, plus `faker==40.43.0` (MIT);
  - dev dependencies: pytest, ruff, mypy;
  - entry points `pilot-build`, `pilot-host`, `pilot-traffic`, `pilot-incidents`, `pilot-env`, `pilot-split`, `pilot-fault`, `pilot-traffic-ctl`;
  - lock with `uv lock --project pilot`;
  - `pilot/README.md` stub.
- [X] T002 [P] Skeleton:
  - `pilot/template/{template.yaml,agent/triage_agent/__init__.py,reference/,infra/}`;
  - `pilot/fills/{default,variant}/`;
  - `pilot/src/pilot_tools/__init__.py`;
  - `pilot/tests/{unit,integration}/`.
- [X] T003 [P] `Makefile`: `check` also runs `ruff check`, `ruff format --check`, `mypy` and `pytest` for the pilot project. Coverage for the pilot is reported separately, with an 80% gate on `pilot_tools` and the template agent.
- [X] T004 [P] Boundary and isolation tests, written first, in `tests/unit/test_pilot_boundary.py`:
  - no `pilot`/`pilot_tools`/`triage_agent` import in `src/adlc`, and no `adlc` import in `pilot/`;
  - from `deploy/compose.yaml`: no pilot service on the `platform` network, no platform service on the `pilot` network, only `jaeger` on both, no published ports for pilot services, no Docker socket mount anywhere.

**Checkpoint**: `make check` runs both projects (the pilot tests are empty).

---

## Phase 2: Foundational (blocks every story)

### Tests first

- [X] T005 [P] Unit tests in `pilot/tests/unit/test_fill.py`:
  - a valid default fill passes;
  - each rule fails with the part named:
    - instructions "1–20,000 characters";
    - every team in the routing rules exists in the team directory;
    - categories only from `access, hardware, software, network, security`;
    - tool bindings only for declared tools;
    - thresholds "numbers in 0–1";
    - `token_budget` "100–8,000";
    - `model_mode` from the infra definition's allowed list.
- [X] T006 [P] Unit tests in `pilot/tests/unit/test_triage.py` for the simulated model:
  - a security signal goes to the security team at P1;
  - a catalogue service goes to its owner team;
  - category keywords give the category's team;
  - an unknown service goes to first line, with the reason;
  - a multi-service incident is marked for review;
  - planted personal data is never echoed;
  - the token budget is enforced;
  - the toxicity and jailbreak counters count the patterns they list.

  Unit tests for the degraded model: deterministic by request id, misroutes the configured share.

### Implementation

- [X] T007 Reference data `pilot/template/reference/service_catalogue.yaml` (about 20 services, each with owner team and category) and `team_directory.yaml` (about 8 teams, with the first-line and security teams marked); `pilot/template/template.yaml` (id `incident-triage`, version, fill points and schemas).
- [X] T008 The agent in `pilot/template/agent/triage_agent/`:
  - app factory (`POST /triage`, `GET /health` with the package hash and model);
  - the mocked tools;
  - the simulated and degraded models;
  - a real OpenAI-compatible client (settings `PILOT_MODEL_URL`, `PILOT_MODEL_NAME`, `PILOT_MODEL_API_KEY`; a non-JSON reply falls back to the simulated model and is counted);
  - the PII pattern check;
  - metrics, including basic pattern-based RAI counters: a fixed toxic-term list on output and known jailbreak phrases on input, labelled as basic;
  - spans `triage.request`, `triage.tool` and `triage.model` with the request id and package hash, and no incident text.
- [X] T009 The default fill `pilot/fills/default/` (instructions, routing rules, tool bindings, thresholds, settings) and a variant fill `pilot/fills/variant/` (one changed routing rule, for canary demos).

**Checkpoint**: the agent triages incidents in-process with the default fill.

---

## Phase 3: User Story 1 – The template builds into one package (P1) 🎯 MVP

- [X] T010 [P] [US1] Write failing tests in `pilot/tests/unit/test_build.py`:
  - two builds of the same fill give the same `sha256:` hash and identical bytes;
  - changing any filled part, any agent file or any infra definition changes the hash;
  - an invalid fill names the part and writes nothing;
  - the manifest lists every file with its hash.
- [X] T011 [US1] Implement `pilot/src/pilot_tools/build.py` (`pilot-build`): fill validation (T005) and a deterministic tar.gz per research R-02 (sorted entries, mtime 0, uid and gid 0, normalised modes, gzip mtime 0), with the archive and manifest written to the registry.
- [X] T012 [P] [US1] Write a failing integration test in `pilot/tests/integration/test_package_runs.py`: a built package, extracted and started as a worker process, answers a synthetic incident, and `GET /health` reports the package hash.

---

## Phase 4: User Story 2 – Environments from the template's infrastructure (P1)

- [X] T013 [P] [US2] Infra definitions `pilot/template/infra/dev.yaml`, `test.yaml` and `prod-sim.yaml` per data-model.md. Dev and test allow `model_mode: [simulated, real]`; prod-sim allows only simulated.
- [X] T014 [P] [US2] Write failing integration tests in `pilot/tests/integration/test_host_environments.py` for a host (`pilot-host --env dev`, in-process app with real worker processes):
  - create for a hash gives running replicas, status with the hash, and a triage answer;
  - create again gives `409`;
  - tear down leaves no worker process;
  - create again gives the same configuration;
  - an unknown hash gives `404` and an undeclared setting `422`, with nothing created;
  - every operation is appended to `environments.jsonl`;
  - `GET /infra` returns each environment's infrastructure definition and version (FR-021).
- [X] T015 [US2] Implement `pilot/src/pilot_tools/host.py` and `workers.py`: extract to a work folder, start and stop uvicorn worker processes on local ports per the infra definition, health checks, records, and `GET /infra`.

---

## Phase 5: User Story 3 – Synthetic incidents (P1)

- [X] T016 [P] [US3] Write failing tests in `pilot/tests/unit/test_incidents.py`:
  - the same seed and size give identical files;
  - every category, priority and edge case is present (`unknown_service`, `multi_service`, `security`, `missing_details`, `duplicate`, `out_of_scope`);
  - every incident has `synthetic: true` and expected team, category and priority;
  - no planted data by default, and planted data only in the requested share, marked;
  - the simulated model routes at least 90% of a seeded 500-incident set to the expected team (SC-005).
- [X] T017 [US3] Implement `pilot/src/pilot_tools/incidents.py` (`pilot-incidents`) with Faker seeded per research R-08.

---

## Phase 6: User Story 4 – Prod-sim rollout and traffic (P1)

- [ ] T018 [P] [US4] Write failing tests:
  - in `pilot/tests/unit/test_split.py`: hash-based assignment gives 15–25% at a 20% share over 500 request ids;
  - in `pilot/tests/integration/test_prodsim.py`:
    - deployments of stable and candidate;
    - `PUT /split` canary, shadow and full;
    - every answer names its package;
    - shadow never returns candidate answers and records them in `shadow.jsonl`;
    - an unknown candidate is refused and the split stays;
    - a failing candidate falls back to stable and is counted;
    - split changes are recorded.
- [ ] T019 [US4] Implement `pilot/src/pilot_tools/split.py` and the prod-sim routes in `host.py` (`/deployments`, `/split`, `/triage`).
- [ ] T020 [P] [US4] Write failing tests in `pilot/tests/integration/test_traffic.py`:
  - the generator against a host holds the rate within ±10% over a short window (the scaled version of SC-004);
  - pause stops new requests;
  - counts for sent, answered, failed and timed out;
  - routing accuracy and the PII leak rate are computed from the expected answers and planted values.
- [ ] T021 [US4] Implement `pilot/src/pilot_tools/traffic.py` (`pilot-traffic`) with an open-loop schedule and the control API per contracts/pilot-api.md.

---

## Phase 7: User Story 5 – Faults (P2)

- [ ] T022 [P] [US5] Write failing tests in `pilot/tests/integration/test_faults.py`:
  - `model_swap` lowers routing accuracy below baseline by the configured margin and revert restores it (SC-005, scaled);
  - `pii_leak` exposes planted data in at least 10% of answers and the check detects it (SC-006), with 0% after revert;
  - a second trigger gives `409`;
  - every trigger and revert is recorded in `faults.jsonl` with its parameters and affected packages and replicas.
- [ ] T023 [US5] Implement the fault routes in `host.py` (switching the workers' model mode or leak setting through a worker admin call) and `pilot-fault`.

---

## Phase 8: User Story 6 – Isolation (P2)

- [ ] T024 [US6] Compose changes in `deploy/compose.yaml`:
  - a `platform` network for every platform service;
  - a `pilot` network for `pilot-dev`, `pilot-test`, `pilot-prodsim`, `pilot-traffic` and `pilot-tools` (profile `tools`);
  - `jaeger` on both;
  - volumes `pilot-packages`, `pilot-records` and `pilot-data` (`/data` in `pilot-tools` and `pilot-traffic`);
  - the pilot's own settings on the pilot services: `PILOT_MODEL_URL`, `PILOT_MODEL_NAME`, `PILOT_MODEL_API_KEY` (empty by default) and the OTLP endpoint, added to `.env.example` with the `PILOT_` prefix, plus a test that no pilot setting shares a name with a platform setting;
  - no published pilot ports;
  - health checks.

  Add `deploy/pilot.Dockerfile` (image `adlc-pilot:0.1.0`, non-root user) and a `deploy/README.md` section. The T004 tests must pass.
- [ ] T025 [US6] `pilot/src/pilot_tools/cli.py`: `pilot-env`, `pilot-split`, `pilot-fault` and `pilot-traffic-ctl` per contracts/pilot-api.md. A live isolation check script `deploy/pilot-isolation-check.sh` tries connections in both directions and reports pass or fail (SC-007).

---

## Phase 9: Polish

- [ ] T026 [P] Update `docs/solution-architecture.md` §14 and the demo script to the Incident Triage Assistant (demo moments unchanged), and `pilot/README.md` (template, fill points, packages, environments, faults, traffic).
- [ ] T027 [P] Run the 003–008 suites and the pilot suites 10 times in a row and record the result.
- [ ] T028 Run `make check` and fix any failure.
- [ ] T029 Live check (quickstart §2):
  - `make up`;
  - build twice (same hash);
  - create the dev and test environments;
  - deploy stable and candidate to prod-sim;
  - canary at 20%, with traffic at 5 per second for 10 minutes (SC-003, SC-004);
  - the model swap and the leak (SC-005, SC-006);
  - the isolation check (SC-007);
  - environment creation time (SC-009).

  Record the results.

---

## Dependencies and execution order

- **Order:** Phase 1, then Phase 2, then the stories.
- **US1** first (packages).
- **US2** needs US1.
- **US3** can run with US1 and US2.
- **US4** needs US2 and US3.
- **US5** needs US4.
- **US6** can start after Phase 1, but its live check needs everything.
- **Phase 9** comes last.

## Parallel examples

- **Phase 1**: T002, T003 and T004 together.
- **Phase 2 tests**: T005 and T006 together.
- **US2–US3**: T013, T014 and T016 together.
- **US4**: T018 and T020 together.

## Implementation strategy

1. **MVP**: Phases 1–3. One package, one hash.
2. **Environments and data**: Phases 4–5.
3. **Rollout, traffic and faults**: Phases 6–7.
4. **Isolation and polish**: Phases 8–9.

Run `make check` and commit at every checkpoint.
