# Contract: telemetry, change, release, retirement evidence (feature 012)

| Source | Fields |
| --- | --- |
| `telemetry` | `online_eval_score`, `pii_leak_count`, `availability_pct`, `cost_per_task_usd`, `monitors {<id>: reporting}`; unmeasured fields absent |
| `change` | `window {start, end}`, `window_requested`, `request_status` |
| `release` | `package_sha256`, `release_date` |
| `retirement` | `credentials_revoked`, `data_disposed`, `unowned_dependants` |

A monitor fires when its threshold expression is true; unevaluable thresholds never fire; one event
per breach episode.
