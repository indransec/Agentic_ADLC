# Contract: Events, outbox and delivery

## Envelope (`events.outbox_event`)

```json
{
  "event_id": "0192f0e2-…",
  "event_type": "T4.rework.implementation",
  "usecase_id": "UC-0001",
  "correlation_id": "UC-0001/lifecycle",
  "causation_run_id": "UC-0001/T4/run-1",
  "payload": {
    "ledger_key": "UC-0001/T4/run-1",
    "status": "rework",
    "root_cause": "implementation",
    "comment": "Tool timeout on claim lookup",
    "target_terminal": null,
    "emits": {"risk_tier": "medium"}
  }
}
```

Payloads carry **references and short decision fields, never artifacts** (SA §6.3). The next
run reads artifacts through the ledger record and the causing run.

## Event types written by this feature

| Event | Written when |
| --- | --- |
| `usecase.submitted` | `submit_usecase` |
| `T<n>.pass`, `T<n>.exception`, `T<n>.terminate` | A run closes with that status |
| `T<n>.escalate` | A run enters `escalated` (a notification event: no terminal subscribes; used for notifications and the journey view) |
| `T<n>.rework.<root_cause>` | A rework close |
| `T<n>.reentry.T<k>` | A pass with a template route resolving to T<k> |
| `T8.event.<name>` | `raise_operational_event` |
| Follow-on event (for example `T7.rollback`) | An event route's `then` destination is an event and `then_when` holds |

## Delivery rules

1. **Ordering**: per use case, in `created_at` order. A pending earlier event blocks later
   ones until it is processed or dead-lettered.
2. **Exactly once**: `Router.handle` and the insert into `events.processed_event` commit
   together. An event id already present there is skipped.
3. **Retries**: after a failed attempt, the next try is 10 s, 1 min, 5 min and then 15 min
   later (scaled by `ADLC_TIME_SCALE`). The fifth failure sets `dead_lettered_at`.
4. **Re-queue**: sets `attempts=0`, `next_attempt_at=now()`, `dead_lettered_at=null`, and
   writes `events.dead_letter_action`.
5. **Wake-up**: `NOTIFY adlc_outbox` on insert, with a polling fallback of
   `ADLC_POLL_INTERVAL` (default 1 s).
