# Contract: REST operations (ADO 7.1 subset)

Base: `http://<host>:<ADO_SIM_PORT>/{organization}/{project}` (ADO: `https://dev.azure.com/...`).
Every operation needs `api-version` (`7.1`, or `7.1-preview.4` for comments, as ADO) and a
personal access token (Basic auth with the token as password, or Bearer). Bodies are JSON;
patches use `application/json-patch+json`. Reference pages: Microsoft Learn,
`https://learn.microsoft.com/rest/api/azure/devops/<area>/<page>?view=azure-devops-rest-7.1`
(cited as `<area>/<page>`). The committed machine-readable form is `ado_sim/contract/openapi.json`.

**Confirmed against the reference (T001, 2026-11-20).** Every "Reference" below resolves to
`https://learn.microsoft.com/en-us/rest/api/azure/devops/<area>/<page>?view=azure-devops-rest-7.1`.
Details taken from the pages: batch and list return `{count, value}` and allow at most 200 ids,
`errorPolicy` is `fail` or `omit`; WIQL also accepts an optional `{team}` path segment (not
served: a listed difference), `timePrecision` and `$top`, and answers `columns` and
`sortColumns` as field references (`referenceName`, `name`, `url`); comments use
`7.1-preview.4`, return `{totalCount, count, comments, nextPage, continuationToken}` and each
comment carries `id`, `workItemId`, `version`, `text`, `createdBy`, `createdDate`, `modifiedBy`,
`modifiedDate`, `isDeleted`, `url`; a work item carries `commentVersionRef` ("the comment
added/edited/deleted in this revision"), so **adding a comment creates a new work item revision**
(its update shows `System.CommentCount` and `System.History`); identities return
`{count, value}` with `id`, `descriptor`, `providerDisplayName`, `isActive` and
`properties.Account` (`{"$type": "System.String", "$value": ...}`).

## Work items (`wit/work-items`)

| Operation | Method and path | Notes | Reference |
| --- | --- | --- | --- |
| Create | `POST /_apis/wit/workitems/${type}` | patch body of `add` operations on `/fields/<ref>` and `/relations/-`; `validateOnly`, `bypassRules` (refused: no rules to bypass), `$expand` | wit/work-items/create |
| Get | `GET /_apis/wit/workitems/{id}` | `fields`, `asOf`, `$expand` (`None`, `Relations`, `Fields`, `Links`, `All`) | wit/work-items/get-work-item |
| List | `GET /_apis/wit/workitems?ids=…` | up to 200 ids; `fields`, `asOf`, `$expand`, `errorPolicy` (`Fail`, `Omit`) | wit/work-items/list |
| Batch | `POST /_apis/wit/workitemsbatch` | body `{ids, fields, asOf, $expand, errorPolicy}`; up to 200 | wit/work-items/get-work-items-batch |
| Update | `PATCH /_apis/wit/workitems/{id}` | patch: `add`, `replace`, `remove`, `test` on `/fields/<ref>`, `/relations/-`, `/relations/<i>`, `/rev`; all-or-nothing | wit/work-items/update |

Responses: `200` with the work item (`id`, `rev`, `fields`, `relations` when expanded, `_links`,
`url`); refusals per research R-02 (`400` invalid, `404` unknown, `412` failed `test`).

## History (`wit/updates`, `wit/revisions`)

| Operation | Method and path | Notes | Reference |
| --- | --- | --- | --- |
| List updates | `GET /_apis/wit/workItems/{id}/updates` | `$top` (default 200), `$skip`; in revision order | wit/updates/list |
| Get update | `GET /_apis/wit/workItems/{id}/updates/{updateNumber}` | | wit/updates/get |
| List revisions | `GET /_apis/wit/workItems/{id}/revisions` | `$top`, `$skip`, `$expand` | wit/revisions/list |
| Get revision | `GET /_apis/wit/workItems/{id}/revisions/{revisionNumber}` | the item exactly as of that revision | wit/revisions/get |

An update: `{id, workItemId, rev, revisedBy, revisedDate, fields: {ref: {oldValue, newValue}},
relations: {added, removed, updated}, url}`.

## Queries (`wit/wiql`)

| Operation | Method and path | Notes | Reference |
| --- | --- | --- | --- |
| Query by WIQL | `POST /_apis/wit/wiql` | body `{"query": "<WIQL>"}`; `$top` up to 20,000; subset in `wiql.md` | wit/wiql/query-by-wiql |

Response: `{queryType: "flat", queryResultType: "workItem", asOf, columns, sortColumns,
workItems: [{id, url}]}`; link queries return `queryType: "oneHop"`, `queryResultType:
"workItemLink"`, `workItemRelations: [{rel, source, target}]`.

## Comments (`wit/comments`, api-version `7.1-preview.4`)

| Operation | Method and path | Notes | Reference |
| --- | --- | --- | --- |
| Add | `POST /_apis/wit/workItems/{workItemId}/comments` | body `{"text": "..."}` | wit/comments/add-comment |
| List | `GET /_apis/wit/workItems/{workItemId}/comments` | `$top` (max 200), `continuationToken`, `order` (`asc`, `desc`) | wit/comments/get-comments |

## Process and classification (`wit/work-item-types`, `wit/fields`, `wit/classification-nodes`)

| Operation | Method and path | Reference |
| --- | --- | --- |
| List work item types | `GET /_apis/wit/workitemtypes` | wit/work-item-types/list |
| Get work item type | `GET /_apis/wit/workitemtypes/{type}` | wit/work-item-types/get |
| List states of a type | `GET /_apis/wit/workitemtypes/{type}/states` | wit/work-item-type-states/list |
| List fields | `GET /_apis/wit/fields` | wit/fields/list |
| Get area tree | `GET /_apis/wit/classificationnodes/Areas` (`$depth`) | wit/classification-nodes/get |

## Identities (`ims/identities`)

| Operation | Method and path | Notes | Reference |
| --- | --- | --- | --- |
| Read identities | `GET /{organization}/_apis/identities` | `searchFilter=General` with `filterValue`, or `identityIds`; returns `{count, value: [{id, descriptor, providerDisplayName, properties.Account, isActive}]}` | ims/identities/read-identities |

ADO serves identities from `vssps.dev.azure.com`; the simulator serves them on its own host (a
listed difference). The adapter takes the identities base URL from its settings.

## Simulator-only

| Operation | Method and path | Notes |
| --- | --- | --- |
| Health | `GET /health` | no authentication; `{"status": "ok"}` |
| Contract | `GET /openapi.json` | no authentication; the published description (equals the committed file) |

Anything else under `/_apis/` answers `404`, as ADO does for unknown routes (FR-020).

## Common rules

- `api-version` is required on every ADO operation; missing or unsupported → `400` naming the
  supported versions (FR-025).
- Limits (FR-026): a field value or comment over 1 MB, more than 500 patch operations, a query over
  32 KB or a body over 5 MB → `400`; more than 200 ids in a list or batch → `400`.
- List and batch `errorPolicy`: `Fail` (default) → `404` if any id is missing; `Omit` → missing ids
  left out (FR-002).
- A link change updates both items in one transaction (FR-012).
- An `{organization}` or `{project}` in the path that is not the seeded one → `404` with an ADO
  error body.

## Errors

ADO's error body: `{"$id": "1", "innerException": null, "message": "...", "typeName": "...",
"typeKey": "...", "errorCode": 0, "eventId": 3000}`. `401` responses carry no detail, never
whether an identity exists (FR-015).
