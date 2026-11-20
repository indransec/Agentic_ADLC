# Data Model: ADO Simulator API (015)

One SQLite file (`ADO_SIM_DB_PATH`), owned by the simulator only (constitution VII). Times are
ISO 8601 text in UTC with microseconds (`2026-11-20T10:15:30.123456Z`). JSON columns hold text.
Created by `ado_sim/src/ado_sim/migrations/0001_initial.sql`.

## Tables

### `schema_version`
| Column | Type | Notes |
| --- | --- | --- |
| version | integer | highest applied migration |

### Process (from the seed file; replaced only by reset)

**`organization`** — `id` (text uuid, PK), `name` (text, unique).

**`project`** — `id` (uuid, PK), `organization_id` (FK), `name` (text, unique per org).

**`area_node`** — `id` (integer, PK), `identifier` (uuid, unique), `project_id` (FK), `name`,
`path` (text, unique, e.g. `Agentic ADLC\Use cases`), `parent_id` (FK, null for the root).

**`work_item_type`** — `name` (PK, e.g. `Epic`), `reference_name`, `description`, `color`.

**`work_item_type_state`** — `type_name` (FK), `name`, `category` (`Proposed`, `InProgress`,
`Resolved`, `Completed`, `Removed`), `color`, `ordinal`; PK (`type_name`, `name`). The Epic's
rows are the terminal stages from the seed file.

**`field`** — `reference_name` (PK, e.g. `System.Title`, `Custom.AdlcDecision`), `name`, `type`
(`string`, `plainText`, `html`, `integer`, `double`, `dateTime`, `boolean`, `identity`,
`treePath`), `read_only` (boolean; system fields the simulator sets).

**`work_item_type_field`** — `type_name` (FK), `reference_name` (FK), `allowed_values` (JSON
list or null); PK (`type_name`, `reference_name`). Which fields each type has.

### Identities and tokens

**`identity`** — `id` (uuid, PK), `display_name`, `unique_name` (text, unique, e.g.
`business.owner@adlc.demo`), `active` (boolean).

**`access_token`** — `id` (integer, PK), `identity_id` (FK), `token_hash` (text, unique;
HMAC-SHA256 with `ADO_SIM_TOKEN_KEY`), `label`, `issued_at`, `revoked_at` (null while valid).
Never holds the token itself (FR-017).

### Work items

**`work_item`** — current state.
| Column | Type | Notes |
| --- | --- | --- |
| id | integer PK | allocated from 1 upward, never reused |
| type_name | FK | |
| rev | integer | current revision, starts at 1 |
| fields | JSON | current values keyed by reference name |
| changed_date | text | equals `fields["System.ChangedDate"]`; indexed for "changed since" |
| state | text | equals `fields["System.State"]`; indexed |
| area_path | text | equals `fields["System.AreaPath"]`; indexed |
| comment_count | integer | |

**`revision`** — one row per revision, append-only.
| Column | Type | Notes |
| --- | --- | --- |
| work_item_id | FK | |
| rev | integer | PK (`work_item_id`, `rev`) |
| fields | JSON | full values as of this revision |
| relations | JSON | full relation list as of this revision |

**`work_item_update`** — one row per change, append-only (ADO's "updates").
| Column | Type | Notes |
| --- | --- | --- |
| work_item_id | FK | |
| id | integer | PK (`work_item_id`, `id`); 1, 2, 3 … per item, in order; the update with `id` 1 is the creation |
| rev | integer | the item's revision after this update; not unique: an update from the other side of a link keeps the current `rev` |
| revision_bearing | 0 or 1 | 1 when this update created a revision; 0 for the other side of a link (T001) |
| revised_by | FK identity | the authenticated changer |
| change_date | text | when the change was made |
| fields | JSON | `{ref: {"oldValue": …, "newValue": …}}`; `oldValue` absent on creation; a comment's update carries `System.CommentCount` and the transient `System.History` |
| relations | JSON | `{"added": [...], "removed": [...], "updated": [...]}` |

An update's `revisedDate` (in the API) is the changed date of the next revision, or
`9999-01-01T00:00:00Z` for the latest one; for a non-revision update it is its own change date
(as ADO, T001).

**`relation`** — current links, both directions stored explicitly.
| Column | Type | Notes |
| --- | --- | --- |
| source_id | FK work_item | |
| target_id | FK work_item | |
| rel | text | `System.LinkTypes.Hierarchy-Forward` (child), `-Reverse` (parent), `System.LinkTypes.Dependency-Forward` (successor), `-Reverse` (predecessor) |
| attributes | JSON | e.g. `{"comment": "..."}`; `isLocked` false |
PK (`source_id`, `target_id`, `rel`). Adding a link on one item adds the reverse on the other in
the same transaction; the item the patch was sent to gets a new revision and update, the other item
an update without a revision (FR-012, T001).

**`comment`** — `id` (integer PK), `work_item_id` (FK), `version` (integer, 1), `text`
(text, stored as given), `created_by` (FK identity), `created_date`, `modified_date`. Adding a
comment also records a new revision of the work item (`System.CommentCount` + 1, and
`System.History` holding the text in that revision only), as ADO's `commentVersionRef` (T001).

## Validation rules (from the spec)

- A field must exist on the item's type (`work_item_type_field`); read-only system fields cannot
  be set by a patch (FR-005).
- `System.State` must be one of the type's states; any state may follow any other (FR-005).
- `System.AreaPath` must name an `area_node`.
- Hierarchy: at most one parent per item; no cycles (walk the parent chain); no self-links; the
  target must exist (FR-013).
- A patch is all-or-nothing; a patch with no effective change creates no revision.
- `rev` increases by exactly one per revision; `changed_date` strictly increases in commit order
  across all items (research R-06, FR-009).
- `revision` and `work_item_update` rows are refused UPDATE and DELETE by triggers; `reset`
  drops and recreates the tables instead (FR-019).

## System fields set by the simulator

`System.Id`, `System.Rev`, `System.WorkItemType`, `System.TeamProject`, `System.CreatedBy`,
`System.CreatedDate`, `System.ChangedBy`, `System.ChangedDate`, `System.CommentCount`; defaults
on create: `System.State` = the type's first state, `System.AreaPath` = the project root,
`System.Reason` = "New". Identity fields are returned as ADO identity references
(`{"displayName", "id", "uniqueName", "url", "imageUrl"}`).
