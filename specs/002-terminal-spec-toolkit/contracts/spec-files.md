# Contract: Spec, catalogue, checklist and playbook files

The schemas in `adlc-specs/schema/` are authoritative. This page shows the shapes and the
additions to TDS Annex B (full list in research R-16 and `schema/DICTIONARY-CHANGES.md`).

## Terminal spec (excerpt of additions)

```yaml
# yaml-language-server: $schema=../schema/terminal.schema.json
terminal:
  metadata: {id: T1, name: Requirements & Outcome, version: "1.0.0", schema_version: "1.1.0",
             purpose: What exactly must the agent achieve?, owner_role: adlc_coe, status: active}
  prerequisites:
    - id: PRE-T1-01
      evidence_ref: T0.status
      condition: 'T0.status in ["pass", "exception"]'
      description: "in [pass, exception]"            # TDS wording kept
      on_missing: block
  controls:
    automated:
      - id: CTL-T1-02
        rule: 'all_rows_numeric(T1.kpis, ["baseline", "target"])'
        description: every KPI has numeric baseline and target
        severity: blocking
    checklist: {ref: checklists/t1.yaml, version: "1.0.0", items: [CHK-T1-01, CHK-T1-02]}
  evidence:
    artifacts:
      - id: kpis
        format: table
        columns: [kpi_id, kpi, baseline, target, unit, measurement_source]
        applicability: {mode: mandatory}
  timeline:
    expected_duration: {low: 3d, medium: 5d, high: 8d}
    reminder_after: 2d
    escalate_after: 10d
    max_rework_cycles: 3
    clarification_sla: 2d
    max_clarification_rounds: 2
    max_auto_retries: 3
```

## Catalogue files (`adlc-specs/shared/<plural>.yaml`)

Every catalogue has `catalogue: <name>`, `version: "x.y.z"` and one list of entries:

| File | Entry fields |
| --- | --- |
| `roles.yaml` | `id`, `description` (001 format; `catalogue`/`version` keys added) |
| `risk_tiers.yaml` | `id` (`low`/`medium`/`high`), `description`, `rank` |
| `events.yaml` | `patterns: [{pattern, description}]` (Annex A.3), `external: [{id, description}]` |
| `root_causes.yaml`, `change_classes.yaml`, `data_classes.yaml`, `model_tiers.yaml` | `id`, `description` (data classes add `rank`) |
| `mcp_servers.yaml` | `id`, `owner_role`, `scopes: [scope]`, `description` |
| `permissions.yaml` | `verbs: [verb]` (Annex A.4), `duty_groups: {group: [pattern]}` |
| `evidence_sources.yaml` | `id` (prefix such as `intake`), `fields: [name]`, `description` |
| `route_destinations.yaml` | `id` (e.g. `human_completion`, `owning_terminal`, `lifecycle_closed`, `rai_board`), `kind` (`human` \| `terminal_resolver` \| `terminating` \| `external`), `description` |
| `predicates.yaml` | `name`, `params: [{name, kind: evidence_ref\|list\|string\|number\|duration\|role}]`, `returns: bool`, `description` |
| `metrics.yaml` | `name`, `class` (quality, rai, cost, latency, reliability, business_kpi), `unit`, `direction` (`higher_is_better` \| `lower_is_better`), `method`, `description` |
| `guardrails.yaml` | `name`, `unit`, `direction` (`max`\|`min`\|`superset`), `tighten_only`, `values: {low, medium, high}`, `proposed_default`, `source` |

## Checklist (`adlc-specs/checklists/t<n>.yaml`)

```yaml
checklist: t1
version: "1.0.0"
items:
  - {id: CHK-T1-01, text: Requirements traceable to T0 problem}
```

## Playbook stub (`adlc-specs/playbooks/<file>.md`)

```markdown
---
id: PB-T1-01
version: "1.0.0"
title: T1 requirements
owner_role: adlc_coe
status: stub
---
Content is authored with the T1 agent (feature 008).
```
