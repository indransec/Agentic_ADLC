# Contract: Change approval and proposed events (feature 012)

| Method and path | Body | Answer |
| --- | --- | --- |
| `GET /api/changes?status=new` | — | Change requests awaiting a decision (for the approver role) |
| `POST /api/changes/{change_id}/decision` | `{approve: bool, comment}` | `200` new record version; `403` without the registry's servicenow owner role; `409` already decided |
| `GET /api/events/proposed` | — | T8 proposed events for the accountable role |
| `POST /api/events/proposed/{run_id}/{event_id}` | `{confirm: bool, comment}` | `200`; confirming raises the operational event; `409` already decided |

Every endpoint needs a session (not in `PUBLIC_PATHS`).
