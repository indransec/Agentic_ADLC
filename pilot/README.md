# Incident Triage Assistant (pilot)

The pilot use case of the Agentic ADLC platform (feature 009; SA §14): the agent the platform
builds (T3), evaluates (T4), assures (T5), deploys (T7) and operates (T8). It is a separate uv
project that never imports the platform, and it runs on its own network.

**What it does.** For an incident (title, description, reporter, affected service, urgency) it
returns a category, a priority, a resolver team and a short reason, using two mocked tools: the
service catalogue (`template/reference/service_catalogue.yaml`) and the team directory
(`template/reference/team_directory.yaml`). Security signals go to Security Operations at P1;
unknown services go to the Service Desk; multi-service incidents are marked for review. It never
closes incidents and never repeats personal data, unless the leak fault is on.

## Golden template (`template/`)

| Part | Filled by T3 |
| --- | --- |
| `template.yaml`: id, version, fill points and their rules | No |
| `agent/triage_agent/`: app, triage, tools, models, PII and RAI checks, spans | No |
| `reference/`: mocked tool data (20 services, 8 teams) | No |
| `infra/dev.yaml`, `test.yaml`, `prod-sim.yaml`: infrastructure definitions | No |
| Fill (`fills/<name>/`): `instructions.md`, `routing_rules.yaml`, `tool_bindings.yaml`, `thresholds.yaml`, `settings.yaml` | **Yes** |

`pilot-build --fill <dir>` validates the fill (a failure names the part) and writes a deterministic
archive of the template and the fill; its sha256 is the **package hash**. The same input always
gives the same hash, and any change gives a new one.

## Environments

`pilot-host --env dev|test|prod-sim` runs one environment and starts packages as worker processes
from the package's own infrastructure definition (no container is created, no Docker socket).

- **dev and test:** `POST /environment` (package hash, declared settings), `GET /environment`,
  `DELETE /environment`, `GET /infra` (the definitions, for feature 010's MCP resources).
- **prod-sim:** `POST /deployments` (stable or candidate), `PUT /split` (shadow, canary at a share,
  or full), `POST /faults/{model_swap|pii_leak}` (trigger or revert), `POST /triage`.

Every operation, split change, fault and shadow answer is appended to JSON Lines records.

## Models

A deterministic simulated model by default. The model swap fault switches to a degraded model that
misroutes a configured share (0.5 by default) of requests. A real OpenAI-compatible model can be
switched on in dev and test (`PILOT_MODEL_URL`, `PILOT_MODEL_NAME`, `PILOT_MODEL_API_KEY`); a
failed or invalid reply falls back to the simulated model and is counted.

## Data and traffic

- `pilot-incidents --seed N --size M [--pii-share P] --out <file>`: reproducible synthetic
  incidents with expected team, category and priority; planted personal data only when asked.
- `pilot-traffic`: a steady open-loop stream to prod-sim; `GET /metrics` gives counts, the actual
  rate, routing accuracy and the personal-data leak rate over a sliding window, per package.

## Commands

`pilot-env`, `pilot-split`, `pilot-fault`, `pilot-traffic-ctl`: see `deploy/README.md`.

## Checks

```bash
cd pilot && uv run pytest     # or `make pilot-check` from the repository root
```
