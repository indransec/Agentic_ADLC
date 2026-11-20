# Known differences from Azure DevOps

The simulator follows the Azure DevOps REST API 7.1 reference for every operation in
`specs/015-ado-sim-api/contracts/operations.md`. This list names every place where it
deliberately behaves differently, or where the reference is silent and the simulator had to
choose. **Every entry is to confirm against real ADO before a real tracker is connected**
(feature 016's adapter settings switch the base URL; nothing else should need to change).

## Where the simulator is served

| Difference | Simulator | ADO | Reason |
| --- | --- | --- | --- |
| Host of identities | `GET /{organization}/_apis/identities` on the simulator's own host | `https://vssps.dev.azure.com/{organization}/_apis/identities` | one process; the adapter takes the identities base URL from its settings |
| Organisations and projects | one of each, from the seed file; any other name answers `404` | many | the platform needs one project |
| WIQL with a team | `/{organization}/{project}/_apis/wit/wiql` only; the `{team}` segment is not served (`404`) | `/{organization}/{project}/{team}/_apis/wit/wiql` too | the platform does not query by team |
| Extra routes | `GET /health` and `GET /openapi.json`, both without a token | none | readiness checks and the published contract |
| `_links.html` | points at `/{organization}/{project}/_workitems/edit/{id}`, which the simulator does not serve yet | the web form of the item | the board and form arrive in features 017 and 018 |

## Statuses the reference does not state (research R-02)

The reference pages list only `200 OK`. The simulator answers with ADO's error body
(`$id`, `innerException`, `message`, `typeName`, `typeKey`, `errorCode`, `eventId`) and:

| Case | Status | `typeKey` |
| --- | --- | --- |
| a `test` operation fails (stale `/rev`) | `412` | `WorkItemRevisionMismatchException` |
| invalid value or state, malformed patch, a limit exceeded | `400` | `VssPropertyValidationException`, `RuleValidationException`, `InvalidArgumentValueException`, `RequestTooLargeException` |
| a field the process does not define, or a read-only one | `400` | `FieldNotFoundException`, `ReadOnlyFieldException` |
| a link that is not allowed (unknown target, second parent, cycle) | `400` | `WorkItemLinkException` |
| WIQL that does not parse, or a construct outside the subset | `400` | `WiqlSyntaxException`, `WiqlUnsupportedException` |
| unknown work item (as ADO, which does not say whether it exists) | `404` | `WorkItemUnauthorizedAccessException` |
| unknown work item type, organisation or project | `404` | `WorkItemTypeNotFoundException`, `OrganizationNotFoundException`, `ProjectDoesNotExistWithNameException` |
| no `api-version`, or one that is not supported | `400` | `VssVersionNotSpecifiedException`, `VssVersionOutOfRangeException` |
| a route the simulator does not serve, or a method it does not serve on a route | `404` | `ResourceNotFoundException` |
| a patch sent without `Content-Type: application/json-patch+json` | `415` | `VssRequestContentTypeNotSupportedException` |
| no token, an unknown token or a revoked one | `401` with an empty body | none |

Error messages are the simulator's own wording; the status and `typeKey` are the contract.

## Behaviour

| Difference | Simulator | ADO | Reason |
| --- | --- | --- | --- |
| Revision limit | none | refuses updates after 10,000 revisions ([DevBlogs 2022](https://devblogs.microsoft.com/devops/work-item-revision-limits/)) | the platform's use cases stay far below it |
| `bypassRules=true` | refused with `400` | allowed for project administrators | the simulator has no rules to bypass |
| State transitions | any state of the type to any other | the process's transition rules | the platform moves Epics between stages; rules belong to the platform's policy, not the tracker |
| `System.Reason` | set when the item is created; not changed by a state change | set from the transition | no transition rules |
| `System.History` | read-only in a patch; a comment fills it in the comment's revision | writable in a patch (adds a discussion comment) | comments are added through the comments operation |
| Link types | parent and child (`System.LinkTypes.Hierarchy-*`) and predecessor and successor (`System.LinkTypes.Dependency-*`); any other type → `400` | many, including related, hyperlinks, artifact links and attachments | what features 016–018 need |
| Comments | add and list; no edit, delete, reactions or mentions | all | what features 016–018 need |
| WIQL `asOf` | the latest changed date the query could see (never later than the query time) | the time the query ran | a complete "changed since" bound for the next poll (research R-06); a poller of real ADO needs an overlap or its own bound |
| Time precision | microseconds (`2026-11-20T10:15:30.123456Z`) | milliseconds | lets a poller pass back the latest `ChangedDate` it saw and miss nothing (research R-06); a reader must accept both |
| Throttling | never; no `429` and no `Retry-After` | throttles heavy callers with `429` and `Retry-After` | a local service with one caller; the adapter must still handle `429` for real ADO |
| Tokens | issued and revoked by `ado-sim token`; no scopes and no expiry; any valid token may call every operation | personal access tokens with scopes and an expiry date, and project permissions | the simulator has no permission model; the platform's own policy decides who may do what |
| Identities | seeded users and one service account; `descriptor` and `subjectDescriptor` are the simulator's (`sim.<uuid>`) | Microsoft Entra or Microsoft accounts with ADO descriptors | no directory |
| Field rules | required fields (`System.Title`, `System.State`, `System.AreaPath`), types, allowed states, read-only system fields | also the process's rules (required-when, defaults, allowed values per field) | the seed file defines types, fields and states only |
| Process changes | from the seed file only; no process or field API for writing | the process API | the process is data the operator seeds |
