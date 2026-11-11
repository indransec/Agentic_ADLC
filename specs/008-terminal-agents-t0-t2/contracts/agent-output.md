# Contract: Builder Agent Requests and Answers (feature 008 additions to feature 006)

## What the agent receives (additions)

- **Tools section.** For each tool binding of the agent:
  - the name (for example `confluence_search`);
  - the description;
  - the argument schema, as the tool describes itself.

  Only the arguments the model may set are listed: `query` and `limit`, or `document` and
  `section`.
- **Tool results.** Each comes back in a `<data source="tool:<name>">` block. A refused call comes
  back as "Tool <name> was refused: <reason>".
- **Output instruction.** It adds the tool request shape and the optional `citations` list.

## What the agent may answer (exactly one JSON object)

```json
{"tool": {"name": "confluence_search", "arguments": {"query": "claims triage SOP", "limit": 5}}}
```

```json
{"clarification": {"questions": ["Who owns the claims history data?"],
  "addressed_role": "business_owner",
  "looked_in": ["sharepoint:/policies", "confluence:/business-capabilities"]}}
```

```json
{"artifacts": {"<artifact id>": [{"<column>": "...", "...": "..."}]},
 "citations": [{"artifact": "data_access", "row": 0, "source": "sharepoint",
   "document": "policies/data-classification.md", "section": "Claims data"}]}
```

## Validation (feature 006 output rules, plus)

- **Citations are optional.** Each one given must:
  - name an artifact in the answer;
  - give a row that exists, if a row is given;
  - match a retrieval of this attempt (same source, document and section).

  Otherwise the answer fails validation and the agent gets a correction.
- **`addressed_role`** must be empty or one of the terminal's human roles.
- **No outcome statuses.** The answer never carries a status. Any key other than `artifacts`,
  `citations`, `clarification` or `tool` fails validation.
