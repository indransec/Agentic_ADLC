# Contract: the `BoardAdapter` port

`src/adlc/engagement/port.py`. Board-neutral; the ADO adapter (`ado.py`) and `FakeBoard`
(`fake.py`) implement it, and both pass `tests/contract/board/` (FR-025). Types are in
[data-model.md](../data-model.md#board-neutral-types-engagementmodelpy).

| Operation | Does | Refusals |
| --- | --- | --- |
| `check() -> BoardInfo` | authenticate as the service account; return the process (types, their states and fields), link types, areas | `BoardAuthFailed`, `BoardUnreachable` |
| `create(type, fields, parent_id=None) -> BoardItem` | create an item (and its parent link) as the service account | `BoardRefused` (unknown field, value) |
| `get(item_id) -> BoardItem` | current state | `ItemNotFound` |
| `get_at(item_id, rev) -> BoardItem` | the item exactly as of a revision | `ItemNotFound` |
| `update(item_id, write: ItemWrite) -> BoardItem` | set and clear fields with `expected_rev` (all or nothing) | `RevisionConflict` (412), `ItemNotFound`, `BoardRefused` |
| `comment(item_id, text) -> None` | add a comment as the service account | `ItemNotFound` |
| `changed_since(watermark) -> ChangePage` | ids of items changed at or after `watermark`, and the answer's `as_of` | `BoardUnreachable` |
| `updates(item_id, after_update_id) -> list[BoardUpdate]` | the item's updates after the given id, in order | `ItemNotFound` |
| `find_identity(unique_name) -> Identity \| None` | look a board user up | |

Rules every adapter keeps:

- No method returns or logs the token; errors carry no field values.
- `changed_since` + `updates` never lose an update committed after the previous `as_of`
  (015 research R-06).
- `update` changes nothing when `expected_rev` is not the current revision.
- Transport failures (timeouts, 5xx, connection refused) are `BoardUnreachable`; 401 is
  `BoardAuthFailed`; both are retried by the caller, never by the adapter beyond one connection
  retry.

## ADO operations (confirmed against 015 by T001, 2026-11-21)

Every operation is served by the simulator (`ado_sim/contract/openapi.json`) and has a fixture
(`ado_sim/contract/fixtures/`). Paths are under `/{organization}/{project}/_apis` except
identities (`/{organization}/_apis`, on `ADLC_BOARD_IDENTITIES_URL`). `api-version=7.1`, comments
`7.1-preview.4`. No gap.

| Port operation | 015 operation | Query used | Fixture |
| --- | --- | --- | --- |
| `check` | `GET wit/workitemtypes`; `GET wit/classificationnodes/Areas` | `$depth=10` | `work_item_types/list`, `areas/get` |
| `create` | `POST wit/workitems/${type}` (JSON Patch; parent as `/relations/-` `System.LinkTypes.Hierarchy-Reverse`) | | `create/epic`, `create/task_with_parent` |
| `get` | `GET wit/workitems/{id}` | `$expand=Relations` | `get/item`, `get/unknown_item` (404) |
| `get_at` | `GET wit/workitems/{id}/revisions/{rev}` | | `revisions/get` |
| `update` | `PATCH wit/workitems/{id}` with `test /rev` first | | `update/fields_and_rev_test`, `update/stale_rev` (412) |
| `comment` | `POST wit/workitems/{id}/comments` | | `comments/add` |
| `changed_since` | `POST wit/wiql` | `timePrecision=true` | `wiql/flat` (`asOf` = latest change seen, 015 R-06) |
| `updates` | `GET wit/workitems/{id}/updates` | `$top=200`, `$skip` | `updates/list`, `updates/get` |
| `find_identity` | `GET identities` | `searchFilter=General&filterValue=<name>` | `identities/search` |
| (any, no token) | | | `any/no_token` (401, empty body) |
