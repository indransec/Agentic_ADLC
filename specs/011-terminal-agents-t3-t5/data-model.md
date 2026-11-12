# Data Model: Terminal Agents T3–T5 (feature 011)

No new tables.

## Catalogue and spec changes

| File | Change | Version |
| --- | --- | --- |
| `adlc-specs/shared/agents.yaml` | T3–T5 model agents with tool bindings; prompt fixes from the live runs | 6.0.0 |
| `adlc-specs/prompts/t3-builder-agent.md` | New; live fixes | 1.1.0 |
| `adlc-specs/prompts/t4-evaluation-agent.md` | New; live fixes | 1.1.0 |
| `adlc-specs/prompts/t5-assurance-agent.md` | New | 1.0.0 |
| `adlc-specs/playbooks/*` (T3–T5) | Real content (t4-evaluation 1.2.0 after the live run) | 1.1.0 |
| `adlc-specs/shared/predicates.yaml` | `rows_match`, `rows_match_value` | 1.1.0 |
| `adlc-specs/shared/evidence_sources.yaml` | `harness` source; `ci` gains `package_hash`, `tests`, `scans`, `observability` | 2.0.0 |
| `adlc-specs/terminals/T3.yaml` | Evidence controls CTL-T3-09..12; CTL-T3-13 (dev runs CI's package) | 4.0.0 |
| `adlc-specs/terminals/T4.yaml` | Evidence controls CTL-T4-11..14; PRE-T4-04 became CTL-T4-15; playbook 1.2.0 | 4.0.0 |
| `adlc-specs/terminals/T5.yaml` | RAI evidence control | 3.0.0 |
| `data/redteam/suite.yaml` | `evidence_metrics` per category | 1.1.0 |

## Evidence sources (from `tools.tool_result`)

See contracts/evidence-sources.md.

## Artifact import provenance

An imported table's provenance (`artifact`, `result_id`, `kind`, `sha256`, `req_id_by`, `rows`)
is kept in the build step's run activity (`run.run_activity.detail.imports`); the artifact
version itself has only the declared columns (contracts/artifact-import.md).

## Pilot data

| File | Holds |
| --- | --- |
| `pilot/datasets.yaml` | Adds `labelled_slice: {size, reviewed_by: synthetic}` per dataset |
| `pilot/licences.yaml` | Licence allowlist for the SBOM check |
| `data/redteam/suite.yaml` (platform) | `evidence_metric` per category (`prompt_injection: injection_success_rate`, `jailbreak: jailbreak_success_rate`) |
