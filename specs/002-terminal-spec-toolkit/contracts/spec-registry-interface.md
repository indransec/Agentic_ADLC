# Contract: `SpecRegistry` read interface

Platform modules read spec data only through this interface (FR-024, FR-025). It reads the
**active** version unless `version` is given. Unknown keys return `()` or `None`; they never
raise or guess.

```text
class SpecRegistry(Protocol):
    terminals_opened_by(event_type: str) -> tuple[TerminalRef, ...]
    outcome_route(terminal_id: str, status: str, root_cause: str | None = None,
                  version: str | None = None) -> RouteTarget | None
    event_route(terminal_id: str, event_type: str, version: str | None = None)
                  -> EventRouteTarget | None
    change_class_route(terminal_id: str, change_class: str, version: str | None = None)
                  -> ChangeClassRoute | None
    timeline(terminal_id: str, risk_tier: str, version: str | None = None)
                  -> TimelinePolicy | None
    entry(terminal_id: str, version: str | None = None) -> RegistryEntry | None
    catalogue(name: str) -> CatalogueEntry | None
```

## Semantics

- **`terminals_opened_by`** matches `event_type` exactly against the trigger subscriptions of
  active versions, sorted by `terminal_id`.
- **`outcome_route`**:
  - With `status = "rework"` and a `root_cause`: returns the root-cause route if present,
    else the plain `rework.route`, else `None`.
  - Other statuses ignore `root_cause`.
  - A disabled status (`not_allowed`) returns `RouteTarget(kind="disabled", ...)`.
- **`RouteTarget.kind`**:
  - `terminal`: destination is `T<n>`.
  - `event`: for example `T9.retire`.
  - `special`: a value from `route_destinations.yaml`, such as `human_completion` or
    `owning_terminal`.
  - `template`: a `${...}` value the orchestrator resolves from evidence (T9 pass).
- **`timeline`**: for `mode: continuous` terminals, `expected_duration` is `None` and
  `continuous` is `True`; reminder and escalation durations are measured from `review_due`.

## Implementations

- `SqlSpecRegistry(engine)`: SQLAlchemy Core queries over the `spec` schema; used with the
  app identity.
- Tests and feature 003 can use `InMemorySpecRegistry.from_bundle(bundle)`, built from
  validated files through the same projection code, so both implementations return identical
  answers (a test asserts this for every demo routing case).

## Demo routing cases (snapshot test, SC-007)

| Moment | Call | Expected |
| --- | --- | --- |
| start | `terminals_opened_by("usecase.submitted")` | `(T0,)` |
| D-2 | `outcome_route("T1", "rework", "requirement")` | terminal `T1`, requires `owner_comment` |
| D-3 | `outcome_route("T4", "rework", "implementation")` | terminal `T3`, requires `defect_log` |
| D-3 | `terminals_opened_by("T4.rework.implementation")` | `(T3,)` |
| D-4 | `timeline("T1", "medium").max_rework_cycles` | `3`; `outcome_route("T1","escalate")` → special `human_completion` |
| D-5 | `outcome_route("T5", "exception")` | terminal `T6`, `recheck_at` `[T6, T8]`, `set_by` `[risk_owner]` |
| D-7 | `event_route("T8", "T8.event.drift")` | terminal `T9` |
| D-7 | `change_class_route("T9", "moderate")` | re-entry `T2` |
| D-9 | `timeline("T2", "medium")` | `max_clarification_rounds = 2`, `clarification_sla` set |
