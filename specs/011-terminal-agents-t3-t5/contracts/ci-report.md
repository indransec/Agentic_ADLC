# Contract: CI Report (pilot-lab `POST /build`, feature 011 research R-04)

```json
{"checks": [{"name": "validate|build|reproducible|smoke|tests|sast|secret_scan|sbom|observability",
             "passed": true, "detail": "..."}],
 "package_hash": "sha256:...",
 "tests": {"package": {"total_count": 0, "passed_count": 0, "failed_count": 0, "coverage_pct": 0.0}},
 "scans": {"sast": {"critical_count": 0, "high_count": 0, "medium_count": 0},
           "secret_scan": {"critical_count": 0, "high_count": 0, "medium_count": 0}},
 "sbom": {"generated": true, "licences_approved": true, "components": [{"name": "", "version": "", "licence": ""}]},
 "observability": [{"signal": "traces|rai_metrics", "emitting": true, "sample_trace_id": "INC-..."}]}
```

`package_hash` is present only when every check passed. The bridge's `ci_run` passes the report
through (plus `commit`).
