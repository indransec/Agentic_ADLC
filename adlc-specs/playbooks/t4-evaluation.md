---
id: PB-T4-01
version: "1.1.0"
title: T4 evaluation
owner_role: adlc_coe
status: active
---
# T4 evaluation

## Purpose

Decide, with evidence from runs, whether the candidate package meets T1's evaluation and RAI
thresholds, T2's budget and T1's latency requirement, and route every defect to the terminal that
caused it.

## Procedure

1. `pilot_env_create` (the test environment runs the use case's candidate), then
   `pilot_env_status` to see it healthy.
2. `dataset_registry_list`; use the registered golden and regression datasets only.
3. `harness_run` the **regression** dataset first: it is the regression pack and gives the
   per-case results you import.
4. `harness_run` the **golden** dataset last: its `catalogue` metrics, `calibration` and `timing`
   are the evidence your threshold, cost and calibration rows are checked against.

## Steps per artifact

1. **golden_dataset_register** (`dataset_id, version, size_count, synthetic_pct, real_pct,
   approver`): one row per dataset you ran; synthetic datasets are 100% synthetic; `approver` null.
2. **test_case_results** (`case_id, req_id, expected, actual, score, result`): **import** it from
   the regression result: `{"import": {"result": "<result_id>", "req_id_by": {"field":
   "category", "map": {"<category>": "<req_id>"}, "default": "<req_id>"}}}`, mapping each category
   to the T1 functional requirement it tests. It must have at least the parameter's minimum cases.
3. **quality_vs_threshold** (`metric, threshold, actual, result`): one row per T1 evaluation
   threshold, `actual` copied from the golden result's `catalogue` for that metric name; a metric
   the harness did not measure has `actual` "not measured" and `result` `fail`.
4. **rai_vs_threshold** (`metric, slice, threshold, actual, result`): the same for each T1 RAI
   threshold (`slice` `all` unless T1 names one).
5. **cost_latency** (`measure, budget, actual, result`): `cost_per_task_usd` against T2's budget
   per task and `p95_latency_ms` against T1's latency requirement, copied from the golden result.
6. **failure_mode_results** (`scenario_id, scenario, observed, safe_fail`): one row per T1 failure
   scenario, observed from the golden result's slices and cases (for example unknown services go
   to first line with review, security incidents are P1); `safe_fail` true only when observed.
7. **defect_log** (`defect_id, severity, root_cause_terminal, status`): one row per failed
   threshold or unsafe failure mode; `root_cause_terminal` is the terminal whose work must change
   (the build terminal for a package defect, the requirements terminal for a wrong threshold);
   `status` open. No defects: one row `none`, severity `none`, status `closed`.
8. **judge_calibration** (`judge, sample_size_count, agreement_rate`): the golden result's
   `calibration`, copied exactly.
9. **regression_pack** (`pack_id, version, case_count`): the regression dataset's id, version and
   case count.
