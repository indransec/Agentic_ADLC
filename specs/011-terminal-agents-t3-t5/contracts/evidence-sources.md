# Contract: Evidence Sources from Recorded Tool Results (feature 011, research R-05)

Read by the SQL evidence provider from `tools.tool_result` of the use case. "Candidate" is the
hash of T3's `candidate_package` (latest closed T3 run), or, in a T3 run, the package CI built
in that run. Missing results: not available (synthetic fallback, labelled).

| Source | From (kind) | Value |
| --- | --- | --- |
| `ci` | latest `ci` of the run, else of the use case | `status` (`green` when every check passed, else `red`), `run_id` (`RES-<n>`), `package_hash`, `tests: {<suite>: {total_count, passed_count, failed_count, coverage_pct}}`, `scans: {<scan>: {critical_count, high_count, medium_count}}` |
| `sbom` | the same `ci` result | `generated`, `licences_approved` |
| `harness` | latest `harness` for the candidate | `metrics: {<catalogue metric>: value}`, `dataset: {id, version, sha256}`, `calibration: {<judge>: {sample_size_count, agreement_rate}}`, `result_id` |
| `redteam` | latest `redteam` for the candidate | `{<evidence_metric>: rate}` per category that names one |
| `dlp` | latest `dlp` for the candidate | `pii_leak_count` (findings) |
