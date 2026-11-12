# Data Model: Pilot Environments

No platform database changes. The pilot keeps files in two volumes: `pilot-packages` (the package
registry) and `pilot-records` (append-only JSON Lines records).

## Golden template (`pilot/template/`)

| Path | Holds | Filled by T3 |
| --- | --- | --- |
| `template.yaml` | Template id (`incident-triage`), version, fill points and their schemas | No |
| `agent/` | The agent: app factory, triage flow, mocked tools, simulated and real model clients, PII check, metrics | No |
| `reference/service_catalogue.yaml` | Services, each with an owner team and category | No |
| `reference/team_directory.yaml` | Teams, what they handle, the first-line and security teams | No |
| `infra/dev.yaml`, `infra/test.yaml`, `infra/prod-sim.yaml` | Infrastructure definitions (below) | No |

### Fill (`fill/`, validated against `template.yaml`)

| File | Content | Rules |
| --- | --- | --- |
| `instructions.md` | The agent's instructions | 1–20,000 characters |
| `routing_rules.yaml` | `security_keywords`, `category_keywords` (category → keywords), `category_teams` (category → team), `priority_rules` | Every team must exist in the team directory; categories from `access, hardware, software, network, security` |
| `tool_bindings.yaml` | Tools the agent may call: `service_catalogue`, `team_directory` | Only tools the template declares |
| `thresholds.yaml` | `min_confidence_for_auto`, `review_on_multi_service` | Numbers in 0–1, booleans |
| `settings.yaml` | `token_budget` (per request), `model_mode` (`simulated` or `real`), `model_name` | Budget 100–8,000; mode from the infra definition's allowed list |

### Infrastructure definition (`infra/<env>.yaml`)

```yaml
environment: prod-sim        # dev | test | prod-sim
version: "1.0.0"
replicas: 2                  # worker processes per package
request_timeout_s: 10
model_modes: [simulated]     # allowed; dev and test also allow real
overridable: {model_mode: [simulated, real]}   # settings a create request may set
splitter: {modes: [shadow, canary, full], default_share: 0.2}   # prod-sim only
```

## Package (registry `pilot-packages/`)

| Item | Rule |
| --- | --- |
| `<hex>.tar.gz` | Deterministic archive (research R-02); `package_hash` = `sha256:<hex>` of these bytes |
| `<hex>.json` | Manifest: `package_hash`, `template_id`, `template_version`, `built_at`, `files` (path → sha256), `fill_summary` |

## Synthetic incident (JSON Lines)

| Field | Rule |
| --- | --- |
| `incident_id` | `INC-<seed>-<n>` |
| `title`, `description` | Text |
| `reporter` | `{name, department, persona}` |
| `affected_service` | A catalogue service id or an unknown name |
| `urgency` | `low`, `medium`, `high` |
| `edge_case` | `none`, `unknown_service`, `multi_service`, `security`, `missing_details`, `duplicate`, `out_of_scope`, `unsafe` (jailbreak or abusive wording; T032) |
| `expected` | `{team, category, priority}` with priority `P1`–`P4` |
| `synthetic` | Always `true` |
| `planted_pii` | `[]`, or the planted e-mail and phone |

## Triage answer

`{incident_id, category, priority, team, reason, review: bool, package_hash, model, tokens}`. The
reason never repeats planted personal data unless the leak fault is active.

## Records (`pilot-records/`, append-only JSON Lines)

| File | One line per |
| --- | --- |
| `environments.jsonl` | Create, status and tear down: `{at, environment, operation, package_hash, settings, outcome, reason?}`; status outcome `ok` (with `healthy`) or `not running` |
| `splits.jsonl` | Split change: `{at, mode, share, stable, candidate, outcome}` |
| `faults.jsonl` | Trigger or revert: `{at, fault, action, parameters, affected: {packages, replicas}, outcome}` |
| `shadow.jsonl` | A shadow answer: `{at, request_id, candidate_hash, answer}` |

Incident files written by `pilot-incidents` go to the `pilot-data` volume (`/data`).
