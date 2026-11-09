# Contract: `adlc-spec` CLI and make targets

## `adlc-spec validate [PATH]`

Validates the spec folder (default `adlc-specs`) at L1–L5.

| Option | Default | Meaning |
| --- | --- | --- |
| `--format text\|json` | `text` | Output format |
| `--baseline-ref REF` | `$ADLC_SPEC_BASELINE_REF`, else `origin/main` | Git ref for L5; a missing ref gives warning `V-24` "baseline unavailable" and no L5-vs-git check |
| `--no-baseline` | off | Skip L5 against git |
| `--min-severity error\|warning\|info` | `info` | Hide findings below this severity in output (exit code is unaffected) |

**Exit codes**: `0` no errors (warnings or info only); `1` one or more errors; `2` usage
error (path missing, bad option).

**Text output**: one line per finding, sorted by file and line, then a summary line.

```text
adlc-specs/terminals/T3.yaml:57:9 L4 V-06 error  tool scope mcp:gitt:branch_write is not in the MCP registry (shared/mcp_servers.yaml)
adlc-specs/terminals/T0.yaml       L5 V-24 error  content changed but version 1.0.0 equals baseline origin/main
2 errors, 0 warnings, 1 info in 26 files (0.8 s)
```

**JSON output**: `{"summary": {"errors": n, "warnings": n, "info": n, "files": n},
"findings": [{"rule_id", "level", "severity", "file", "path", "line", "column",
"message"}]}`.

## `adlc-spec register [PATH]`

Validates (as above, without the git baseline), then registers into the data store named by
`ADLC_DB_*` using the schema-owner identity (`DatabaseSettings`, feature 001).

| Option | Default | Meaning |
| --- | --- | --- |
| `--dry-run` | off | Do everything inside the transaction, print the plan, then roll back |

**Exit codes**: `0` registered or "no changes"; `1` validation errors or registration refused
(for example, changed content under the same version, or retiring a pinned version), with
nothing written; `2` usage or configuration error (settings errors use the 001 format).

**Output**: one line per item and a summary.

```text
T3 1.0.0 → 1.1.0  registered (deprecated 1.0.0)
guardrails 1.0.0  unchanged
spec registration: 1 registered, 24 unchanged, 0 refused
```

## Make targets (added to contracts/make-targets.md of 001)

| Target | Does |
| --- | --- |
| `make spec-validate` | `uv run adlc-spec validate adlc-specs` (CI: baseline `origin/main`) |
| `make spec-register` | `uv run adlc-spec register adlc-specs` against `.env` |
| `make check` | lint → typecheck → **spec-validate** → test → migration-check → secret-scan |
| `make up` | as before; Compose runs `migrate` → `register` → `api` |
