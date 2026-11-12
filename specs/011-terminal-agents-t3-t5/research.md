# Research: Terminal Agents T3–T5 (feature 011)

## R-01 Agents, prompts and playbooks

**Decision.** `t3-builder-agent` (coding tier), `t4-evaluation-agent` and `t5-assurance-agent`
(reasoning tier) become model agents (agents catalogue 4.0.0) with new prompts (1.0.0) and real
playbook content for the playbooks their specs name (t3-build, golden-template,
prompt-versioning, t4-evaluation, golden-dataset, judge-calibration, t5-assurance, llm-red-team,
privacy-impact-assessment, regulatory-mapping). Each agent is bound to the tools its terminal's
tool scopes allow (feature 010 catalogue names). No subagents (SA §7.1 allows two for T3; not
needed with tools doing the work).

**Rationale.** Same pattern as feature 008: content and registry entries, no terminal names in
code.

## R-02 Step limits for acting agents

**Decision.** Tier defaults rise to 16 steps for `coding` and 14 for `reasoning` (one model call
per step; a tool call per step). T3 needs about 10–14 steps (list, read, write, pull request, CI,
possibly a fix and CI again, environment, status, final answer).

**Alternatives.** Per-terminal overrides in settings (they name terminals; kept for operators,
not as defaults).

## R-03 The example fill on `main` (FR-014)

**Decision.** `pilot-lab` `GET /layout` also returns the template's example fill (the files of
`pilot/fills/default`); the bridge's repository initialisation commits them on `main` instead of
empty files. T3 adapts them on its branch.

## R-04 CI reports what T3's controls read (FR-005)

**Decision.** `pilot-lab` `POST /build` adds, after the four existing checks:
- **tests**: the package suite (the smoke cases plus a scored golden subset) with total, passed,
  failed and line coverage of the template's agent code measured with `coverage` while the suite
  runs in-process;
- **sast**: `bandit` over the template's agent code, counts by severity;
- **secret_scan**: pattern scan of the fill and the template (keys, tokens, private-key headers,
  passwords in URLs), counts by severity;
- **sbom**: the package's runtime distributions with versions and licences, and whether every
  licence is in the pilot's allowlist (`pilot/licences.yaml`);
- **observability**: during the smoke cases, whether request and tool spans and the RAI counters
  were emitted, with a sample request id.

CI `status` is `green` only when every check passed.

**New pilot dependencies.** `coverage` 7.x (Apache-2.0), `bandit` 1.8.x (Apache-2.0).

## R-05 Real evidence sources (FR-010, FR-011)

**Decision.** The SQL evidence provider answers `ci`, `sbom`, `harness`, `redteam` and `dlp` from
`tools.tool_result`, using the latest result of that kind for the use case's current candidate
(for `ci`: the latest CI result of the run, else of the use case):

| Source | Value |
| --- | --- |
| `ci` | `{status, run_id, package_hash, tests: {suite: {total_count, passed_count, failed_count, coverage_pct}}, scans: {scan: {critical_count, high_count, medium_count}}}` |
| `sbom` | `{generated, licences_approved}` from the CI result |
| `harness` | `{metrics: {catalogue metric: value}, dataset, calibration}` |
| `redteam` | `{<metric named by the suite>: rate}` (`injection_success_rate`, `jailbreak_success_rate`) |
| `dlp` | `{pii_leak_count}` |

The red-team suite names the evidence field per category (`evidence_metric`), so no category
names are in code. Synthetic evidence stays the labelled fallback when no result exists.

## R-06 The harness reports catalogue metrics and calibration (FR-006, FR-008)

**Decision.** Besides its own metrics, `harness_run` returns `catalogue`: the metric-catalogue
names it measures (`task_success_rate` = every scored field right; `answer_correctness_rate` = the
first scored field right; `error_rate`; `toxicity_rate`; `pii_leak_count`; `tokens_per_task_count`;
`cost_per_task_usd`; `p50_latency_ms`; `p95_latency_ms`; `judge_agreement_rate`). A dataset
declares a `labelled_slice` (size, human-reviewed; synthetic in the MVP, labelled so); the
calibration compares the scorer's verdicts on the slice with verdicts against the reviewed labels
and returns `{judge: deterministic-scorer, sample_size_count, agreement_rate}`. Metrics the
harness does not measure are absent; T4 writes them as "not measured".

## R-07 Measured values are checked against recorded results (FR-012)

**Decision.** A new predicate `rows_match(table, key_column, recorded)`: for every row whose key
is in `recorded` (a map from key to a value or to a map of column values), each matching column
must equal the recorded value (numbers within 0.001); a row with a recorded key and a different
value fails, naming the row. New blocking controls (specs 3.0.0):

| Terminal | Control |
| --- | --- |
| T3 | `rows_match(T3.test_results, "suite", ci.tests)`, `rows_match(T3.security_build_checks, "scan", ci.scans)`, `T3.candidate_package.sha256 == ci.package_hash` |
| T4 | `rows_match(T4.quality_vs_threshold, "metric", harness.metrics)`, `rows_match(T4.rai_vs_threshold, "metric", harness.metrics)`, `rows_match(T4.judge_calibration, "judge", harness.calibration)` |
| T5 | `rows_match(T5.rai_assurance, "rai_metric", harness.metrics)` |

`harness.metrics` here is the catalogue map, keyed by metric name with the value under the
artifact's measured column (`actual`, `t4_actual`), which the control names.

## R-08 Large measured tables are imported from a recorded result

**Decision.** For a table of per-case results (T4 `test_case_results`, at least
`param.eval_cases_min` rows), the agent may return
`{"import": {"result": "<result id>", "req_id_by": {"field": "<expected field>", "map": {...},
"default": "<req id>"}}}` instead of rows. The platform expands it from the recorded result's
cases (`case_id`, `expected`, `actual`, `score`, `result`), assigns `req_id` by the agent's
mapping, and records the import (result id and hash) with the artifact version. Evidence tools
return their `result_id` to the agent.

**Rationale.** A model cannot reliably copy hundreds of rows; the agent still decides which
result and how cases trace to requirements (constitution III), and the values cannot differ from
what was measured (V).

## R-09 Reference use cases

**Decision.** Only `it-service-desk` matches the pilot's golden template (incident triage); it
runs `until: T5`. The other two stay `until: T2`. Offline: recorded agent replies plus the real
bridge over the fake pilot (feature 010 test support). Live: `adlc-replay` against the running
stack (orchestrator container, dev model).

## R-10 Rework context

**Decision.** A T3 rework run already receives the trigger evidence (defect log and owner
comment, feature 006 context pack); T4's `defect_log` rows with `root_cause_terminal` are the
reviewer's input for the rework route. No new mechanism.
