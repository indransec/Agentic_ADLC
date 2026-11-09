# Data Model: Terminal Spec Toolkit (002)

This feature has two layers: **files** in `adlc-specs/`, which are the source of truth and are
reviewed in Git, and **tables** in schema `spec`, which are written only by registration and
read by the platform. Names follow SA Annex A.6.

## Files (`adlc-specs/`)

| File | Entity | Key | Notes |
| --- | --- | --- | --- |
| `terminals/T<n>.yaml` | Terminal spec | `metadata.id`, `metadata.version` | TDS Annex B plus the additions in research R-16; `schema_version: "1.1.0"` |
| `shared/<plural>.yaml` | Catalogue | `catalogue`, `version` | One per catalogue (see contracts/spec-files.md); entries keyed by `id` or `name` |
| `checklists/t<n>.yaml` | Checklist | `id` (`t<n>`), `version` | `items: [{id: CHK-T<n>-<nn>, text}]` |
| `playbooks/<file>.md` | Playbook | front matter `id`, `version` | Stub body allowed; content hash covers the whole file |
| `schema/*.json` | Schemas | file name | `terminal.schema.json`, `checklist.schema.json`, `catalogues/<name>.schema.json` |
| `schema/DICTIONARY-CHANGES.md`, `CONVERSION.md` | Records | — | Reviewed with specs; not registered |

## Tables (schema `spec`, migration `0002`)

Every table is owned by `adlc_owner`. `adlc_app` has `SELECT` only. Deletes and truncates are
refused for every identity. Updates are refused except for registry status transitions
(research R-11).

### `spec_registry`

| Column | Type | Rule |
| --- | --- | --- |
| `spec_registry_id` | bigint identity PK | |
| `terminal_id` | text | `^T[0-9]+$` |
| `version` | text | semver; unique with `terminal_id` |
| `status` | text | `active` \| `deprecated` \| `retired`; one `active` per `terminal_id` (partial unique index) |
| `schema_version` | text | dictionary version the spec conforms to |
| `spec_yaml` | text | original file text |
| `spec_json` | jsonb | normalised content (research R-09) |
| `content_hash` | text | `^sha256:[0-9a-f]{64}$` |
| `trigger_events` | text[] | from `trigger.on` |
| `emitted_events` | text[] | events this version can emit (research R-06) |
| `registered_at` | timestamptz | default `now()` |
| `deprecated_at`, `retired_at` | timestamptz null | set only by the permitted status transition |

**State transitions**: `active → deprecated`, `active → retired`, `deprecated → retired`. A
transition to `retired` is refused while `usecase_spec_pin` references the row.

### `spec_catalogue`

Same shape and rules as `spec_registry`, keyed by `catalogue_name` instead of
`terminal_id`: `spec_catalogue_id`, `catalogue_name`, `version`, `status`, `content_json`,
`content_hash`, `registered_at`, `deprecated_at`, `retired_at`. There is one active version
per `catalogue_name`.

### `playbook_registry`

| Column | Type | Rule |
| --- | --- | --- |
| `playbook_registry_id` | bigint identity PK | |
| `playbook_id` | text | `^PB-(T[0-9]+\|SH)-[0-9]{2}$`; unique with `version` |
| `version` | text | semver |
| `path` | text | repo-relative |
| `content_hash` | text | sha256 of file bytes |
| `registered_at` | timestamptz | |

### Projection tables

Each projection table references `spec_registry_id`. Its rows are inserted with their
registry row and never changed.

| Table | Columns (besides `spec_registry_id`) | Source in spec |
| --- | --- | --- |
| `spec_trigger` | `event_type` | `trigger.on[]` |
| `spec_outcome_route` | `outcome_status`, `root_cause` (null unless rework by cause), `destination_kind` (`terminal` \| `event` \| `special` \| `template`), `destination`, `alternatives` text[], `requires` text[], `recheck_at` text[], `set_by` text[], `notify` text[], `condition` text | `outcome_model.*` |
| `spec_event_route` | `event_type`, `destination_kind`, `destination`, `immediate` text[], `then_destination`, `notify` text[], `condition` | `outcome_model.event_routes` |
| `spec_change_class` | `change_class`, `reentry_terminal`, `path` text[], `retrospective` text[], `within` interval | `change_classes` |
| `spec_timeline` | `risk_tier` (`low`\|`medium`\|`high`), `expected_duration` interval null, `continuous` bool, `reminder_after` interval, `escalate_after` interval null, `escalate_at_window_end` bool, `max_rework_cycles` int, `clarification_sla` interval, `max_clarification_rounds` int, `max_auto_retries` int | `timeline` (one row per tier, with untiered values repeated) |

Unique keys: `spec_trigger (spec_registry_id, event_type)`;
`spec_outcome_route (spec_registry_id, outcome_status, coalesce(root_cause, ''))`;
`spec_event_route (spec_registry_id, event_type)`;
`spec_change_class (spec_registry_id, change_class)`;
`spec_timeline (spec_registry_id, risk_tier)`.

### `usecase_spec_pin` (created here, written by 003)

| Column | Type | Rule |
| --- | --- | --- |
| `usecase_id` | text | `^UC-[0-9]{4}$` |
| `terminal_id`, `version` | text | FK to `spec_registry (terminal_id, version)` |
| `pinned_at` | timestamptz | |
| `pinned_reason` | text | e.g. `T0 start`, `T9 upgrade` |

PK `(usecase_id, terminal_id)`. Grants on this table (insert and update for re-pinning) are
decided in 003; here `adlc_app` gets `SELECT` only.

## In-memory model (`spec_toolkit`)

- **`SpecBundle`**: every loaded file (path, raw text, data, location index, L1/L2 status) plus
  typed catalogue views. Built once per validation run.
- **`Finding`**: `rule_id`, `level` (`L1`–`L5`), `severity` (`error` \| `warning` \| `info`),
  `file`, `path` (JSON pointer), `line`, `column`, `message`. Any `error` makes validation
  exit 1.
- **`Rule`**: `id`, `level`, `severity`, `summary`, `check(bundle) -> Iterable[Finding]`.
- **Read results** (frozen dataclasses): `TerminalRef(terminal_id, version)`,
  `RouteTarget(kind, destination, alternatives, requires, recheck_at, set_by, notify,
  condition)`, `EventRouteTarget(kind, destination, immediate, then_destination, notify,
  condition)`, `ChangeClassRoute(reentry_terminal, path, retrospective, within)`,
  `TimelinePolicy(...)`, `RegistryEntry(...)`, `CatalogueEntry(name, version, content)`.
