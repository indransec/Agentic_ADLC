# Contract: commands, settings and seed (additions to 015)

| Command | Does | Exit codes |
| --- | --- | --- |
| `ado-sim password set <unique-name>` | ask for a page password twice (no echo; or `--stdin`), at least 12 characters, store its hash | 0, 1 unknown or service identity, 2 too short or mismatch |
| `ado-sim password set --all` | one password for every identity except the service account (hashed per user) | 0, 2 |
| `ado-sim password clear <unique-name>` | remove the page password | 0, 1 unknown |

Settings and seed additions: [data-model.md](../data-model.md). A seed without `board` still
serves the API; the pages say the board is not configured.
