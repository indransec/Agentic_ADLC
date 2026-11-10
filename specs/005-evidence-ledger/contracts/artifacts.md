# Contract: Artifact versions and edits

## Versions written by the orchestrator

| When | Producer | Rule |
| --- | --- | --- |
| `agent_result` with artifacts (each build attempt) | `agent`, `agent:<run_id>`, attempt = `auto_retries + 1` | One version per artifact whose content differs from the current version |
| `escalation_completed` | `person` (the completing account) | Same rule |

A version records its `derived_from_version` (the current version before it) and
`schema_valid`: true when the content is a list of mappings and every row has every declared
column. The run's inline artifacts become the latest versions' content.

## Service operations (`LedgerService`; feature 007 exposes them)

| Operation | Who | When | Effect | Errors |
| --- | --- | --- | --- | --- |
| `edit_artifact(actor, run_id, artifact_id, rows)` | A role of the applicable sign-off rule, or an accountable role of the terminal | `awaiting_sign_off` or `escalated` | A new `person` version, unless the content is unchanged; bumps the run's `version`; writes an activity row (`sign_off`, outcome `edited`). While awaiting sign-off it also clears earlier pass approvals, withdraws a pending waiver (status `rejected`, comment "withdrawn: artifact edited"), and re-runs the automated controls, storing their results | `NotAuthorised`, `InvalidTransition` (wrong state), `UnknownArtifact` |
| `upload_spreadsheet(actor, run_id, artifact_id, data, file_name)` | Same | Same | Rows are parsed (contracts below), then a new version with the file attached | `InvalidUpload` (unreadable, no fitting sheet), `AttachmentRefused` (type or size), plus the above |
| `attach_file(actor, run_id, artifact_id, data, file_name, media_type)` | Same | Same | A new version with the same content plus the attachment | `AttachmentRefused`, plus the above |
| `artifact_history(run_id, artifact_id)` | Any signed-in person | Any | Versions with producer, time, hash, schema validity, attachments | — |

## Spreadsheet parsing

The sheet used is the one named after the artifact id, else the only sheet. Row 1 holds the
column names (trimmed). Each later non-empty row becomes a mapping:

- numbers stay numbers;
- booleans stay booleans;
- dates become ISO text;
- empty cells become empty text.

Formulas are read as their cached values. A workbook with several sheets and none named after
the artifact is refused.
