# Contract: WIQL subset

The simulator answers exactly this subset of Work Item Query Language; any other construct is
refused with `400` and a message naming it (FR-010, FR-011). Keywords are case-insensitive;
field names are written in brackets (`[System.State]`).

## Flat queries

```
SELECT <field> [, <field>]* FROM workitems
[WHERE <condition>]
[ORDER BY <field> [ASC|DESC] [, <field> [ASC|DESC]]*]
```

- Selected fields only shape the `columns` of the answer; the result is always the matching ids.
- Conditions: `<field> <op> <value>` with `=`, `<>`, `<`, `<=`, `>`, `>=`; `<field> IN (<v>, …)`;
  `[System.AreaPath] UNDER '<path>'`; combined with `AND`, `OR`, `NOT`, and parentheses.
- Values: single-quoted strings, integers, dates (`'2026-11-20T10:00:00Z'` or `'2026-11-20'`),
  and the macros `@project` (the current project) and `@today` (with `- <n>` days).
- Order by any field that is stored for every item; `System.ChangedDate` and `System.Id` are
  indexed.
- `$top` (query parameter) limits the result, at most 20,000 (as ADO).

Examples the later features use:

```
SELECT [System.Id] FROM workitems
WHERE [System.TeamProject] = @project AND [System.ChangedDate] >= '2026-11-20T10:15:30.123456Z'
ORDER BY [System.ChangedDate] ASC, [System.Id] ASC

SELECT [System.Id], [System.Title] FROM workitems
WHERE [System.WorkItemType] = 'Epic' AND [System.AreaPath] UNDER 'Agentic ADLC\Use cases'
  AND [System.State] <> 'Closed'
```

`System.ChangedDate` comparisons use the full stored precision (microseconds). The answer's
`asOf` is the latest changed date the query could see; changed dates increase in commit order
across all items, so a reader that passes the previous answer's `asOf` back as
`[System.ChangedDate] >= '<asOf>'` (with `timePrecision=true`) misses nothing and de-duplicates by
(id, rev) (research R-06). A bound taken from items read after the query is not safe: another
item can change in between with an earlier date.

## Link queries (parent and child)

```
SELECT [System.Id] FROM workitemLinks
WHERE ([Source].[System.Id] = <id> OR [Source].[System.WorkItemType] = '<type>')
  AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'
  [AND [Target].[System.WorkItemType] = '<type>']
MODE (MustContain)
```

Returns `workItemRelations` pairs: one with `source: null` per matching source, then one per
link (as ADO's one-hop queries).

## Refused (examples)

`ASOF`, `EVER`, `CONTAINS`, `CONTAINS WORDS`, `IS EMPTY`, `WAS EVER`, `MODE (Recursive)` and
`MODE (MayContain)`, `FROM workitemLinks` with link types other than hierarchy, and any field not
defined in the process.
