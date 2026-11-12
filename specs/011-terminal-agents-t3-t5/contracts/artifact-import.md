# Contract: Importing a Table from a Recorded Result (feature 011, research R-08)

In its final answer, instead of rows for a table artifact, an agent may give:

```json
{"import": {"result": "RES-42",
            "req_id_by": {"field": "category", "map": {"network": "FR-03"}, "default": "FR-01"}}}
```

- `result` must be an evidence result of the same run (returned by a tool as `result_id`) whose
  kind offers case rows (`harness`).
- Rows become `{case_id, req_id, expected, actual, score, result}`: `expected`/`actual` are the
  scored fields joined (`team=a; priority=P3`), `score` is the share of scored fields right,
  `result` is `pass` or `fail`; `req_id` comes from `req_id_by` on the row's expected `field`.
- The build step's run activity records the import (artifact, result id, its sha256, kind, the mapping, row count); the artifact version has only the declared columns.
- Any other shape, an unknown or foreign result, or a table without case columns is an invalid
  output, returned to the agent for correction (feature 006).
