# Research: Pilot Environments

## R-01 The pilot is a separate project that never imports the platform

**Decision**: the pilot lives in `pilot/` as its own uv project (`pyproject.toml`, `uv.lock`),
Python 3.12, with two parts:

- **Golden template** (`pilot/template/`): what goes into a package:
  - the agent code (fixed);
  - the reference data of its mocked tools;
  - the fill rules;
  - the infrastructure definitions.
- **Pilot tooling** (`pilot/src/pilot_tools/`), which is not packaged:
  - the package builder;
  - the environment host;
  - the traffic generator;
  - the fault commands;
  - the incident generator.

The root `make check` runs the pilot's lint, types and tests too. A boundary test checks that
`pilot/` imports nothing from `adlc` and `src/adlc` imports nothing from `pilot`.

**Rationale**: FR-017 and SA §14. The pilot is "any team's agent": its own dependencies, image and
tests.

**Alternatives**: a package inside `src/` would share dependencies and make accidental imports
easy.

## R-02 A package is a deterministic archive of the template and its fill

**Decision**:
- **Contents:** `pilot-build --fill <dir>` validates the fill (FR-002) and writes a `.tar.gz` of:
  - `template/agent/`;
  - `template/reference/`;
  - `template/infra/`;
  - `template/template.yaml`;
  - the fill, under `fill/`.
- **Deterministic archive:** entries sorted, mtime 0, uid and gid 0, modes normalised, gzip header
  mtime 0.
- **Identity:** the package id is `sha256:<hex>` of the archive bytes.
- **Registry:** packages are written to a registry folder (volume `pilot-packages`) as
  `<hex>.tar.gz` with a manifest: template version, fill values summary, file list and hashes.

**Rationale**: FR-003 and SC-001. The same input gives the same bytes, and any filled part changes
them. The archive holds the agent code itself, so what T4 tested is what T7 deployed (D-6).

## R-03 Environments are hosts that run packages as processes (no Docker socket)

**Decision**:
- **Hosts:** each environment is a long-running container (`pilot-dev`, `pilot-test`,
  `pilot-prodsim`) running `pilot-host --env <name>`. On request, the host extracts a package from
  the registry to a work folder and starts it as one or more worker processes (the package's app
  factory served on local ports), as its infrastructure definition says.
- **Control API:** create, status and tear down.
- **No container creation:** a host never creates containers, so no Docker socket is mounted
  anywhere.

**Rationale**:
- **Security:** mounting the Docker socket gives a container root on the host; the platform must
  stay secure by default (constitution XI).
- **Determinism:** environments are still created deterministically from the template (FR-019,
  FR-020).

**Alternatives**: a controller creating containers through the Docker API, which needs the socket.
That is post-MVP, alongside Kubernetes namespaces (SA §15).

## R-04 Infrastructure definitions are declarative and versioned with the template

**Decision**: `template/infra/<env>.yaml` gives, per environment:
- the replica count;
- the worker count;
- the request timeout;
- the model mode allowed (simulated, or real when the setting is on);
- the settings a request may override, with their allowed values;
- for prod-sim, the splitter modes and the default share.

The host reads only these. A request with an undeclared setting is refused (FR-019). The
definitions are plain files, so feature 010 can serve them as MCP resources (FR-021).

## R-05 The simulated model and the model swap

**Decision**: the default model is a deterministic simulated triage that applies the fill's
routing rules, in order:

1. A security signal (keywords such as data loss or breach) goes to the security team at P1.
2. The affected service is looked up in the service catalogue tool; its owner team is used.
3. Otherwise, category keyword rules give a category and its default team.
4. Otherwise, the first-line team, with "unknown service" in the reason.

Priority comes from urgency and impact keywords. The reason names the rule and the tool result.

- **Model swap fault:** switches the instances to a degraded simulated model. It skips the
  catalogue lookup and, for a deterministic share of requests (by request id), picks a wrong team
  from the category rules, so routing accuracy drops by a predictable margin and recovers on
  revert.
- **Real model:** when the setting is on (dev and test only), the instructions from the fill and
  the tool results go to an OpenAI-compatible chat endpoint configured in the pilot's own
  settings (`PILOT_MODEL_URL`, `PILOT_MODEL_NAME`, `PILOT_MODEL_API_KEY`, default GPT-4o mini).
  The reply must be one JSON assignment; anything else falls back to the simulated model and is
  counted.

**Rationale**: the clarification (simulated by default), SC-005 (the swap is measurable), and
cost: steady traffic costs nothing.

## R-06 Prod-sim splitter

**Decision**: the prod-sim host keeps a stable package and an optional candidate, each with its
replicas, and routes `POST /triage` by mode:

- `full`: everything goes to the stable package.
- `canary`: a request goes to the candidate when a deterministic hash of the request id falls
  under the share.
- `shadow`: everything goes to the stable package; a copy goes to the candidate in the
  background, and its answer is recorded but never returned.

Every answer carries `package_hash`. `PUT /split` refuses a hash that is not in the registry
(FR-012), and every change is appended to the split history. If the candidate fails, the stable
package answers and the failure is counted.

**Rationale**: SC-003 (15–25% at a 20% share over 500 requests). Hash-based assignment is
deterministic and even.

## R-07 Traffic generator, online accuracy and personal-data checks

**Decision**:
- **Generator:** `pilot-traffic` is a small asyncio service. It sends generated incidents to
  prod-sim at a configured rate, with an open-loop schedule so the rate holds even when answers
  are slow. Its control API sets the rate, starts and pauses.
- **Metrics:** it knows each incident's expected team, so it computes:
  - **online routing accuracy** over a sliding window (FR-016);
  - the **personal-data leak rate**: answers that contain an incident's planted values, or match
    the e-mail and phone patterns.

  It reports sent, answered, failed and timed-out counts. `GET /metrics` returns these as JSON for
  feature 010's telemetry server; traces go to the shared collector.
- **No Locust:** Locust (in the build plan's stack) is not used. A single endpoint at a steady,
  open-loop rate is a few dozen lines with `httpx`, and Locust would bring gevent into the pilot.

## R-08 Synthetic incidents

**Decision**:
- **Generator:** `pilot-incidents --seed N --size M [--pii-share P]` uses Faker (MIT, `40.43.0`,
  at least two weeks old) with a seeded `random.Random` and `Faker.seed_instance`. It writes JSON
  Lines.
- **Each incident:**
  - id, title, description, reporter (name, department, persona);
  - affected service (from the catalogue, or unknown);
  - urgency and edge case;
  - expected team, category and priority;
  - `synthetic: true`;
  - `planted_pii` (empty unless requested).
- **Edge cases:**
  - unknown service;
  - ambiguous or multi-service;
  - security-sensitive;
  - missing details;
  - duplicate;
  - unsafe or out-of-scope text.

  The share of each is fixed per seed.
- **Planted data:** an e-mail address and phone number in the description, only for a share of
  incidents when requested (FR-009). A golden set for T4 is a seeded file.

## R-09 Networks and isolation

**Decision**:
- **Two networks:** Compose gets a `platform` network (all platform services) and a `pilot`
  network (the pilot hosts, the traffic generator and the package builder). Docker bridge networks
  are isolated from each other, so names and addresses on one are not reachable from the other
  (FR-013).
- **Jaeger** joins both, as the shared trace collector: observability, not a platform service the
  spec protects.
- **Feature 010's MCP servers** will be the only services on both networks besides Jaeger.
- **Ports:** the pilot publishes no host ports. The demo operator uses `docker compose run` or
  `exec` with the pilot CLIs.
- **Tests:**
  - a static test of the Compose file: no pilot service on `platform`, no platform service on
    `pilot`;
  - a live check: connections in both directions fail (SC-007).

## R-10 Traces and records

**Decision**:
- **Traces:** the package's app emits OpenTelemetry spans (`triage.request`, `triage.tool`,
  `triage.model`) with the request id and package hash. The exporter goes to Jaeger (service
  `pilot-triage-<env>`), with no incident text in spans.
- **Records:** the hosts append JSON Lines records to a `pilot-records` volume:
  - environment operations (FR-019);
  - split changes (FR-012);
  - faults (FR-015).
- **No platform database:** the pilot has no platform database.

## R-11 Documents to update

SA §14 and the demo script name the Travel Claims Assistant; they are updated to the Incident
Triage Assistant (the clarification). The demo moments are unchanged. The `golden-template`
playbook (PB-T3-02) stays a stub until feature 011.
