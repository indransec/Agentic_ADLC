# Contract fixtures

One file per case: `<operation>/<case>.json`. Each holds a request and the response the
simulator gives on a freshly seeded database (`seed/demo.yaml`). `tests/contract/test_fixtures.py`
replays every file (SC-001); feature 016's adapter tests reuse them as recorded exchanges.

```json
{
  "operation": "update",
  "case": "stale_rev",
  "description": "what the case shows",
  "reference": "Microsoft Learn page of the operation (7.1)",
  "identity": "unique name of the caller, or null when the request carries no token",
  "setup": [ { "request": "sent first, in order; each answers 200" } ],
  "request": {
    "method": "PATCH",
    "path": "/adlc-demo/Agentic%20ADLC/_apis/wit/workitems/1",
    "query": { "api-version": "7.1" },
    "headers": { "Content-Type": "application/json-patch+json" },
    "body": [],
    "auth": false
  },
  "expected": { "status": 412, "body": {} }
}
```

- `auth` is present only when it is `false`; otherwise the caller adds
  `Authorization: Bearer <token>` for `identity`. **No fixture holds a token.**
- Work item ids in paths are literal: on a fresh database they start at 1, in the order of
  `setup`.
- `expected.body` is `null` when the response has no body (`401`).

## Body patterns

| Pattern | Matches |
| --- | --- |
| `"<int>"` | any integer (work item, update and comment ids) |
| `"<string>"` | any string (error messages, continuation tokens) |
| `"<datetime>"` | an ISO 8601 UTC time ending in `Z` |
| `"<uuid>"` | a lower-case UUID (identity ids) |
| `"<url>"` | an absolute `http(s)` URL (they name the server's own host) |
| `"<any>"` | any value |
| `"<more>"` as a list's last element | the list starts with the elements before it and may hold more |
| anything else | equal |

Objects match key for key: the same keys, each value matching. Error messages are `<string>`
because ADO's wording is not part of the contract; the status and `typeKey` are.
