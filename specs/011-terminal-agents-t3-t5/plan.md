# Implementation Plan: Terminal Agents T3–T5

**Branch**: `011-terminal-agents-t3-t5` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-terminal-agents-t3-t5/spec.md`

## Summary

T3, T4 and T5 become model agents that act through feature 010's tools (research R-01):
- **T3** adapts the golden template's example fill (on `main` from the start, R-03) on its
  branch, runs CI until green, provisions dev with the built hash and reports the build
  artifacts.
- **T4** provisions test with the bound candidate, runs the golden and regression datasets,
  compares the harness's catalogue metrics with T1's thresholds, logs defects and records the
  regression pack.
- **T5** runs the red-team suite and the personal-data scan, reads controls and identities, and
  builds the assurance artifacts; gaps go through the existing exception and waiver path.

**Evidence becomes real** (R-05): `ci`, `sbom`, `harness`, `redteam` and `dlp` are read from the
recorded tool results. **Copied numbers are checked** (R-07): a new predicate `rows_match` and
new blocking controls compare artifact values with those results. **Large per-case tables are
imported** from a recorded result by the agent's choice (R-08).

**Pilot side**: CI reports tests with coverage, SAST, secret scan, SBOM and observability (R-04);
the harness reports catalogue metrics and judge calibration (R-06).

## Technical Context

**Language/Version**: Python 3.12, uv, ruff, mypy strict, pytest; the pilot project.

**Primary Dependencies**: existing platform stack (LiteLLM gateway, MCP SDK, SQLAlchemy). Pilot
gains `coverage` 7.x (Apache-2.0) and `bandit` 1.8.x (Apache-2.0).

**Storage**: no new tables. Artifact imports are recorded in the artifact version's provenance
(feature 005 record content); evidence results are 010's `tools.tool_result`.

**Testing**:
- **Unit (test first):** `rows_match`; evidence mapping of `ci`, `sbom`, `harness`, `redteam`,
  `dlp`; table import expansion; harness catalogue metrics and calibration; CI report shape.
- **Integration:** T3, T4, T5 runs with scripted agent replies through the real runtime, tool
  gate, run tokens and the bridge over the fake pilot; controls reading real evidence; a weaker
  candidate routed to rework; an exception with waiver at T5; out-of-scope tool calls refused.
- **Pilot suite:** CI checks (tests, coverage, SAST, secret scan, SBOM, observability), the
  example fill in the layout, dataset calibration.
- **Replay:** `it-service-desk` offline through T5; live on the dev model.

**Target Platform**: unchanged services; images rebuilt.

**Constraints**: no terminal names in code; agents never write statuses or the attestation;
measured values checked against recorded results; T6–T9 stay stubs.

**Scale/Scope**: 3 agents, 3 prompts, about 10 playbooks, about 6 new controls, 1 predicate, 5
evidence sources.

### New dependencies and licences (constitution VIII)

| Dependency | Use | Licence |
| --- | --- | --- |
| coverage 7.x (pilot) | Line coverage of the package suite in CI | Apache-2.0 |
| bandit 1.8.x (pilot) | SAST of the template's agent code in CI | Apache-2.0 |

### Demo moments supported (constitution XII)

| Moment | Supported by |
| --- | --- |
| D-3 rework routed by root cause | T4 defect log with root-cause terminal; weaker candidate → T3 |
| D-5 exception with waiver | T5 gap → reviewer recommends exception → waiver approver |
| D-6 tested = deployed | T3 hash = CI hash; T4/T5 bound to the candidate |
| Demo steps 4–6 | Real T3, T4, T5 |

## Constitution Check

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | Agents, prompts, playbooks, controls and evidence fields are spec and catalogue content; code stays terminal-neutral | Pass |
| II Superset, not values | Thresholds from T1 and guardrails; datasets and red-team suite as data | Pass |
| III Agents build, humans decide | Agents produce artifacts and choose imports; statuses, waivers and attestations stay human | Pass |
| IV Separation of duties | Tools only within the terminal's scopes (010), bound hashes | Pass |
| V Evidence-first | Measured values checked against recorded results; imports recorded with their source | Pass |
| VI Deterministic first | CI, harness, red-team, scan and the checks are deterministic; the model writes judgement | Pass |
| VII Interfaces | Evidence sources and the import contract are generic | Pass |
| VIII Open source | coverage and bandit, Apache-2.0 | Pass |
| IX Test first | Predicate, evidence mapping, import and CI report test-first | Pass |
| X Observable | Agent runs, tool calls and evidence reads traced and recorded | Pass |
| XI Secure | No new scopes; outputs labelled as data; agents cannot deploy | Pass |
| XII Simplicity | No subagents; one predicate; one import shape | Pass |
| XIII Naming | Annex A names (`rows_match`, catalogue metric names) | Pass |

**Post-design re-check**: Pass.

## Project Structure

```text
specs/011-terminal-agents-t3-t5/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/ evidence-sources.md  artifact-import.md  ci-report.md
└── checklists/
adlc-specs/prompts/t3-builder-agent.md  t4-evaluation-agent.md  t5-assurance-agent.md
adlc-specs/playbooks/*.md                 # the T3–T5 playbooks with real content
adlc-specs/shared/agents.yaml             # 4.0.0: model agents with tool bindings
adlc-specs/shared/predicates.yaml         # rows_match
adlc-specs/shared/evidence_sources.yaml   # harness source; ci/sbom/redteam/dlp fields
adlc-specs/terminals/T3.yaml T4.yaml T5.yaml   # 3.0.0: evidence controls, playbook versions
src/adlc/policy/predicates/evaluation.py  # rows_match
src/adlc/policy/evidence.py               # ci, sbom, harness, redteam, dlp from tools.tool_result
src/adlc/agents/output.py (import)        # table import expansion and provenance
src/adlc/agents/mcp_tools.py              # result_id in evidence tool output
src/adlc/config/settings.py               # tier step defaults
src/adlc/tools/bridge/evaluation.py       # catalogue metrics, calibration, case rows
src/adlc/tools/bridge/git_repo.py         # example fill on main
data/redteam/suite.yaml                   # evidence_metric per category
data/reference_usecases/it-service-desk.yaml   # until T5
tests/fixtures/replays/it-service-desk/t3-*.jsonl t4-*.jsonl t5-*.jsonl
pilot/src/pilot_tools/lab.py ci_checks.py  # CI report (tests, coverage, SAST, secrets, SBOM, observability)
pilot/datasets.yaml  pilot/licences.yaml
```

## Complexity Tracking

| Choice | Why | Simpler alternative rejected because |
| --- | --- | --- |
| Table import from a recorded result | Hundreds of per-case rows | A model cannot copy them reliably; platform-written tables were not chosen |
| A new predicate | One generic check for every copied value | Per-artifact checks would name terminals in code |
