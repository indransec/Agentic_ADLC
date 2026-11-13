# Contract: Dashboard API (feature 013)

Every route needs a session (not in `PUBLIC_PATHS`); every signed-in person may read.

| Method and path | Answer |
| --- | --- |
| `GET /dashboard/usecases/{id}/journey` | `{usecase, lanes: [{terminal_id, name, runs: [bar]}], arrows: [arrow], panel: {escalations, exceptions}, time_scale}` |
| `GET /dashboard/usecases/{id}/kpis` | `{kpis: [kpi value]}` |
| `GET /dashboard/activity?usecase_id&terminal_id&actor_type&step&limit` | `[activity entry]` newest first (limit default 200, max 1000) |
| `GET /dashboard/runs/{run_id}/timeline` | `{activity: [...], attempts: [{attempt, model_calls: [...], tool_calls: [...]}]}` |
| `GET /dashboard/portfolio?risk_tier&status` | `{usecases: n, kpis: [kpi value]}` |
| `GET /dead-letters` (extended) | adds `attempts`, `last_error`, `causation_run_id`, `usecase_id`, `requeues` |
| `GET /dead-letters/{event_id}` | payload and history (CoE only) |

Unknown use case or run: `404`. No session: `401`. Dead letters without the CoE role: `403`.
