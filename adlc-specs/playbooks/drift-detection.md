---
id: PB-T8-03
version: "1.1.0"
title: Drift detection
owner_role: adlc_coe
status: active
---
# Drift detection

## Purpose

Show whether answer quality or behaviour has moved from the T4 baseline, by how much, and where.

## Steps

1. For the baseline metric (T4 `eval_baseline`), compare the period's reading with the baseline
   value: one `drift_report` row with `metric` the observability metric, `slice` `all`,
   `baseline` the T4 value, `current` the reading, `delta` current minus baseline.
2. A delta beyond the baseline tolerance is drift. The quality monitor raises the drift event on
   its own; record it in `raised_events` with status `raised`. Never raise it yourself.
3. Drift with no monitor covering it (for example a slice the monitor does not see): propose an
   event (`raised_events` status `proposed`, `event_type` `drift`).
