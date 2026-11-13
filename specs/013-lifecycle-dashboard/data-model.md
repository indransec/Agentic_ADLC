# Data Model: Lifecycle Dashboard (feature 013)

No new tables. Read models (computed on read):

- **Lane**: terminal id, name, ordered by terminal number; runs.
- **Run bar**: run id, terminal, run number, state, final status, opened, closed, duration (wall),
  current owner (agent | reviewer | role awaited), time split.
- **Arrow**: from run, to run, kind (rework | reroute | exception | event | re-entry | terminate |
  pass), cause (root cause and comment, waiver id and expiry, monitor id and value, change class),
  actor, at.
- **Activity entry**: at, use case, run, terminal, actor type, actor, step, outcome, duration.
- **KPI value**: id, name, definition, value or null, unit, per terminal values where applicable.
- **Dead letter**: event id, type, use case, causation run, attempts, last error, dead-lettered at,
  payload (on request), re-queue history.
