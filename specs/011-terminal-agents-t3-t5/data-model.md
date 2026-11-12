# Data Model: Terminal Agents T3–T5 (feature 011)

No new tables.

## Catalogue and spec changes

| File | Change | Version |
| --- | --- | --- |
| `adlc-specs/shared/agents.yaml` | T3–T5 agents: `implementation: model`, prompts, tool bindings | 4.0.0 |
| `adlc-specs/prompts/t3-builder-agent.md`, `t4-evaluation-agent.md`, `t5-assurance-agent.md` | New | 1.0.0 |
| `adlc-specs/playbooks/*` (T3–T5) | Real content | 2.0.0 |
| `adlc-specs/shared/predicates.yaml` | `rows_match(table, key_column, recorded, measured_column?)` | minor |
| `adlc-specs/shared/evidence_sources.yaml` | `harness` source; `ci` gains `package_hash`, `tests`, `scans`; `dlp`, `redteam` unchanged fields | major |
| `adlc-specs/terminals/T3.yaml`, `T4.yaml`, `T5.yaml` | New evidence controls (research R-07); playbook versions | 3.0.0 |

## Evidence sources (from `tools.tool_result`)

See contracts/evidence-sources.md.

## Artifact import provenance

An imported table's artifact version records, in its content, `imported_from: {result_id,
result_sha256, kind}` and the agent's `req_id_by` mapping (contracts/artifact-import.md).

## Pilot data

| File | Holds |
| --- | --- |
| `pilot/datasets.yaml` | Adds `labelled_slice: {size, reviewed_by: synthetic}` per dataset |
| `pilot/licences.yaml` | Licence allowlist for the SBOM check |
| `data/redteam/suite.yaml` (platform) | `evidence_metric` per category (`prompt_injection: injection_success_rate`, `jailbreak: jailbreak_success_rate`) |
