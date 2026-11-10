# Contract: Predicate library

Every predicate in `adlc-specs/shared/predicates.yaml` is implemented with exactly its
catalogued parameters and return type. Arguments are evaluated values:

- **table**: a list of row mappings;
- **ref**: any evidence value;
- **lists**: CEL lists.

Every "every row" check on an empty table fails with the reason `table is empty`.

When a check fails, the predicate states the reason (contracts/policy-engine.md step 4), naming
the table, the row number (1-based) and the column. "Numeric", "truthy" and "open row" are
defined in contracts/evidence.md.

## Tables

| Predicate | True when | Failure reason names |
| --- | --- | --- |
| `all_rows_in(table, column, allowed)` | Every row's column value is in `allowed` | Row, value |
| `all_rows_have(table, columns)` | Every row has a non-empty value in each column | Row, column |
| `all_rows_numeric(table, columns)` | Every row's columns are numeric | Row, column, value |
| `all_rows_true(table, column)` | Every row's column is truthy | Row |
| `all_rows_match(table, column, value)` | Every row's column equals `value` (trimmed) | Row, value |
| `column_mean / column_min / column_max(table, column)` | (number) Mean, minimum or maximum; an empty table or a non-numeric value is an error | — |
| `no_open_rows(table, column, values)` | No open row has its column in `values` | Row |
| `all_required_artifacts_present()` | Every mandatory artifact of the run's spec is present, as are conditional ones whose `when` holds. "Present" means at least one row, with every declared column as a key | Artifact, column |

## Records, signatures, waivers, directory

| Predicate | True when |
| --- | --- |
| `evidence_exists(ref)` | `ref` is available and not empty (a non-empty table, text or mapping, or a number) |
| `is_signed(ref)` | `ref` comes from a terminal whose latest closed run is `pass` or `exception` (signed under its sign-off rule) |
| `is_frozen(ref)` | `ref` comes from a closed run (its ledger record exists) |
| `is_live(ref)` | `ref`'s run closed `pass` or `exception`, and every row with a `status` column says `live` |
| `is_provisioned(ref)` | `ref` is a mapping with `provisioned` truthy |
| `is_pinned(ref)` | `ref` is non-empty text and neither `latest` nor a wildcard (or a mapping with `pinned` truthy) |
| `in_directory(person)` | The directory knows the account |
| `approved_by(ref, role)` | `ref`'s `approved_by` list contains `role`, or `ref`'s run has a sign-off by that role |
| `all_statuses_in(terminals, statuses)` | Each listed terminal's latest closed status is in `statuses` |
| `no_waiver_expiring_before(date)` | No approved waiver of the use case expires before `date` |
| `no_expired_waivers()` | No approved waiver of the use case has an expiry before today |
| `waiver_expiring_within(period)` | Some approved waiver expires within `period` from now |

## Design and build

| Predicate | True when |
| --- | --- |
| `every_req_mapped(requirements, decisions)` | Every `req_id` appears in some decision row's `req_ids` (a list, or comma or space separated) |
| `every_req_traced(requirements, trace, column)` | Every `req_id` has a trace row with the same `req_id` and a non-empty `column` |
| `all_tools_registered_or_flagged(contracts)` | Every row's `mcp_server` is in the MCP server catalogue, or is `new` |
| `token_budget_within_nfr(budget, nfrs)` | Every budget row has numeric `max_tokens` and `max_cost_usd`. If an NFR with category `cost` exists, each `max_cost_usd` is ≤ its numeric `target` |
| `data_classes_within(strategy, approval)` | Every strategy row's `classification` ranks ≤ the highest approved classification (approval rows with `access_status` `approved`; ranks from the data class catalogue) |
| `hitl_covered(autonomy, hitl)` | Every autonomy row with `hitl_required` truthy has a HITL row for the same `action` |
| `scan_clean(checks, scan, levels)` | The row with `scan` = the given scan exists, and `<level>_count` is 0 for each level |
| `permissions_subset(matrix, design)` | Every matrix row's `resource` appears in the design table's `control` or `layer` column (the designed resources) |
| `any_design_deviation(conformance)` | Some row has a non-empty `deviation` other than `none` |

## Evaluation and assurance

| Predicate | True when |
| --- | --- |
| `all_metrics_meet_thresholds(results, thresholds)` | For every threshold row (`metric`, `operator`, `threshold`), a result row has the same `metric`, and `actual <operator> threshold` holds (operators `>=`, `>`, `<=`, `<`, `==`) |
| `no_critical_threshold_missed(quality, rai)` | No row in either table has `result` `fail` together with a `critical` marker (a `critical` column truthy, or `severity` `critical`) |
| `cost_within_budget(measured, budget)` | Every measured row whose `measure` contains `cost` has `actual` ≤ the largest `max_cost_usd` in the budget |
| `latency_within_nfr(measured, nfrs)` | Every measured row whose `measure` contains `latency` has `actual` ≤ the smallest `target` of the `latency` NFRs |
| `judge_disputed(calibration)` | Some row has a truthy `disputed` column. Without one, it is false with the reason "no dispute recorded" (*CoE to confirm: the T4 calibration table has no dispute column yet; only an escalate condition uses this predicate, and that condition is not automated in the MVP*) |
| `scenario_passed(table, scenario)` | The row with `scenario` = the given scenario exists and its `result` is `pass` |
| `no_unmitigated_critical(threats)` | No row has `residual_risk` `critical` (or `high`) together with a `result` other than `mitigated` or `pass` |
| `assurance_disagreement(attestation)` | The rows' `decision` values are not all the same |
| `unacceptable_residual_risk(register)` | Some row's `decision` is `unacceptable` or `reject` |

## Operations and change

| Predicate | True when |
| --- | --- |
| `alerts_cover(monitoring, kpis, signals)` | Every `kpi` (`kpis.kpi`) and every `signal` (`signals.signal`) has a monitoring row whose `signal` matches and has a non-empty `alert_threshold` |
| `go_no_go_disputed(authorisation)` | The rows' `decision` values are not all the same |
| `within_window(window)` | `window.start` ≤ now ≤ `window.end` |
| `hash_matches(a, b)` | Both carry the same hash. The hash of a value is its `sha256`, `deployed_hash` or `hash` field, or the first row's `sha256` |
| `within_baseline_tolerance(metrics, baseline, stage)` | The stage's rows all have `result` `pass`, and `baseline` is available |
| `no_breach_in_stage(metrics, stage)` | No row of that stage has `result` `fail` or `breach` |
| `rollback_failed(log)` | Some row whose `stage` contains `rollback` has a `result` other than `pass` or `success` |
| `open_incident(log, severities)` | Some open row has its `severity` in `severities` |
| `exceeds_threshold(signal, thresholds, metric)` | The threshold row for `metric` exists, and `signal` is worse than its `threshold` under its `operator` |
| `below_nfr(signal, nfrs, category)` | `signal` < the numeric `target` of the category's NFR |
| `below_baseline(signal, baseline)` | `signal` < `baseline` (a number, or a mapping with `value`) minus its `tolerance` (default 0) |
| `above_budget_for(signal, budget, period)` | `signal` (a series of `{at, value}`) is above the largest `max_cost_usd` at every point within `period` |
| `kpi_below_target_for(kpis, values, reviews)` | Some KPI's last `reviews` values are all below its `target` |
| `all_monitors_reporting()` | The telemetry source reports every monitor as reporting (`telemetry.monitors` all truthy) |
| `regression_within_baseline(report, baseline)` | The report rows all have a `status` other than `fail`, and `baseline` is available |
| `repeated_sev1(log)` | More than one row has `severity` `sev1` |
| `reentry_consistent(assessment)` | Each row has a `change_class` from the change class catalogue, and its `reentry_terminal` is at or before the class's catalogue re-entry terminal |
| `class_at_least_if(assessment, components, minimum)` | If any row's `affected_components` names one of the components, its `change_class` ranks ≥ `minimum` (catalogue order) |
| `classification_disputed(assessment)` | The rows assign more than one distinct `change_class` |
| `has_change_class(assessment, change_class)` | Some row's `change_class` equals `change_class` |

Each predicate has unit tests with at least one passing table and one failing table, and the
failing case's reason is asserted (SC-003).
