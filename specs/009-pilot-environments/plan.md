# Implementation Plan: Pilot Environments

**Branch**: `009-pilot-environments` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-pilot-environments/spec.md`

## Summary

The pilot, an **Incident Triage Assistant**, is a separate uv project in `pilot/` that never
imports the platform.

**Golden template** (`pilot/template/`):
- a fixed agent that assigns an incident to a team, using a mocked service catalogue and team
  directory;
- a deterministic simulated model (a real OpenAI-compatible model can be switched on in dev and
  test);
- per-environment infrastructure definitions;
- fill rules. T3 fills configuration only: instructions, routing rules, tool bindings, thresholds,
  token budget and model settings.

**Packages:** `pilot-build` validates a fill and writes a deterministic archive. Its sha256 is the
package hash.

**Environments:** three host containers (dev, test, prod-sim) start packages as processes from the
infrastructure definitions, with create, status and tear-down operations (no Docker socket).
Prod-sim adds a shadow, canary and full splitter and the two faults (a model swap and a
personal-data leak).

**Traffic generator:** sends synthetic incidents at a steady rate and measures online routing
accuracy and the personal-data leak rate.

**Incident generator:** Faker with a seed produces reproducible incidents with expected answers.

**Isolation:** a separate `pilot` network; only Jaeger, and later feature 010's MCP servers, sit on
both networks. Records are append-only JSON Lines.

## Technical Context

**Language/Version**: Python 3.12, uv, ruff, mypy strict, pytest (the pilot has its own
`pyproject.toml` and `uv.lock`).

**Primary Dependencies (pilot project)**:
- FastAPI and uvicorn (the agent app and the hosts);
- httpx (the traffic generator and the real model client);
- pydantic;
- ruamel.yaml;
- the OpenTelemetry SDK and OTLP exporter.

These are the same licences and pinned versions as the platform. One new library:
**Faker 40.43.0** (MIT).

**Storage**: none in the platform database. Two volumes: `pilot-packages` (the registry) and
`pilot-records` (append-only JSON Lines records).

**Testing**:
- **Unit:**
  - fill validation;
  - deterministic packaging (two builds, same hash; one changed part, different hash);
  - the simulated model's routing (at least 90% on a seeded golden set);
  - the degraded model's drop;
  - the PII check;
  - incident reproducibility;
  - splitter shares.
- **Integration:**
  - a host running a package as processes (create, status, triage, tear down);
  - prod-sim split, shadow and faults;
  - the traffic generator against a host.
- **Static:**
  - the Compose network isolation;
  - the import boundary between `adlc` and `pilot`.
- **Live:** the quickstart, including connection attempts across the networks.

**Target Platform**: Docker Compose. New image `adlc-pilot:0.1.0` (`deploy/pilot.Dockerfile`).
Services `pilot-dev`, `pilot-test`, `pilot-prodsim`, `pilot-traffic` and `pilot-tools` (a profile
for commands), on the `pilot` network.

**Performance Goals**:
- triage under 200 ms with the simulated model;
- an environment running within 2 minutes (SC-009);
- traffic within ±10% of the rate (SC-004).

**Constraints**:
- no platform imports;
- no Docker socket;
- no host ports for the pilot;
- synthetic data only;
- no platform secrets in pilot settings.

**Scale/Scope**:
- 1 agent and 2 mocked tools;
- about 20 services and 8 teams in the reference data;
- 3 environments;
- 2 faults.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| Faker 40.43.0 | Synthetic incidents (build plan stack) | MIT |

Locust (build plan stack) is not used: one endpoint at a steady open-loop rate needs no load
framework (research R-07).

### Demo moments supported (constitution XII)

| Moment | Supported by |
| --- | --- |
| D-6 What T4 tested is what T7 deployed | One package, one hash, in every environment (US1, US2, US4) |
| D-7 T8 event, T9 classification, re-entry | Model swap fault and online routing accuracy (US5) |
| Demo steps 4–9 | Template and provisioning (T3), test environment (T4, T5), prod-sim rollout (T7), traffic (T8) |

**Post-MVP**: containers per environment through an orchestrator API; the optional document
check; a second agent.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | No platform code changes; the pilot names its own domain only (teams, services, categories) | Pass |
| II Superset, not values | The pilot's values live in its fill and reference data, not in platform specs | Pass |
| III Agents build, humans decide | The pilot assigns; it never closes incidents; overrides stay with people | Pass |
| IV Separation of duties | Separate network; platform reaches the pilot only through feature 010's declared paths | Pass |
| V Evidence-first | Package hash covers code, fill and infrastructure; append-only records for operations, splits and faults | Pass |
| VI Deterministic first | Environments come from fixed definitions; no model writes infrastructure; simulated model by default | Pass |
| VII Interfaces | Hosts and traffic expose small HTTP contracts that feature 010 wraps as MCP | Pass |
| VIII Open source | Faker (MIT); no Locust | Pass |
| IX Test first | Packaging, fill validation, routing, splitter and incident generation are written test-first | Pass |
| X Observable | Traces per request and tool with request id and package hash; metrics for accuracy and leaks | Pass |
| XI Secure | No Docker socket, no host ports, no platform secrets, synthetic data only, PII never echoed outside the fault | Pass |
| XII Simplicity | Processes not containers per environment; no load framework; one agent | Pass |
| XIII Naming | Services `pilot-*`, files and fields per Annex A | Pass |

**Post-design re-check**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/009-pilot-environments/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/pilot-api.md
├── checklists/
└── tasks.md
```

### Source Code (repository root)

```text
pilot/
├── pyproject.toml  uv.lock  README.md
├── template/                         # the golden template (goes into every package)
│   ├── template.yaml                 # id, version, fill points and schemas
│   ├── agent/triage_agent/           # app factory, triage flow, tools, models, pii, metrics, tracing
│   ├── reference/                    # service_catalogue.yaml, team_directory.yaml
│   └── infra/                        # dev.yaml, test.yaml, prod-sim.yaml
├── fills/default/  fills/variant/    # the default fill and a second one for canary demos
├── src/pilot_tools/                  # not packaged
│   ├── build.py                      # pilot-build: fill validation, deterministic archive, registry
│   ├── host.py  workers.py  split.py # pilot-host: environments, workers, splitter, faults, records
│   ├── traffic.py                    # pilot-traffic
│   ├── incidents.py                  # pilot-incidents (Faker)
│   └── cli.py                        # pilot-env, pilot-split, pilot-fault, pilot-traffic-ctl
└── tests/{unit,integration}/
deploy/pilot.Dockerfile
deploy/compose.yaml                   # pilot network and services; platform network; jaeger on both
tests/unit/test_pilot_boundary.py     # adlc ↔ pilot imports; compose network isolation
docs/solution-architecture.md         # §14 and the demo script: Incident Triage Assistant
Makefile                              # check runs the pilot project too
```

**Structure Decision**: the pilot is a separate project with its own lock and image. The platform
gains only Compose services, networks and two static tests.

## Complexity Tracking

| Choice | Why | Simpler alternative rejected because |
| --- | --- | --- |
| A second uv project (`pilot/`) | The pilot must be "any team's agent" with its own dependencies (FR-017) | A package inside `src/` would share the platform's dependencies and invite imports |
