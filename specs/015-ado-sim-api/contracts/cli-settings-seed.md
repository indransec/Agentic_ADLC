# Contract: commands, settings and the seed file

## Commands (`ado-sim`, from `ado_sim/`)

| Command | Does | Exit codes |
| --- | --- | --- |
| `ado-sim migrate` | create the database file if missing and apply pending schema migrations | 0, 2 settings error |
| `ado-sim seed --file <yaml> [--if-new]` | load the seed file into an empty database (refuses if work items exist); with `--if-new`, do nothing when the database is already seeded | 0, 1 refused, 2 invalid file |
| `ado-sim reset --yes` | empty every table and seed again from `ADO_SIM_SEED_FILE`; refused without `--yes` | 0, 1 refused |
| `ado-sim token issue <unique-name> [--label <text>]` | print a new token for the identity, once | 0, 1 unknown identity |
| `ado-sim token revoke <token-id>` | revoke a token | 0, 1 unknown id |
| `ado-sim token list [<unique-name>]` | list token ids, identities, labels, issue and revoke times; never tokens | 0 |
| `ado-sim serve` | run the API on `ADO_SIM_PORT` (waits for the database file, migrates nothing) | — |
| `ado-sim export-openapi [--check]` | write `contract/openapi.json`, or with `--check` fail if it differs | 0, 1 differs |

## Settings (environment, prefix `ADO_SIM_`)

| Name | Default | Notes |
| --- | --- | --- |
| `ADO_SIM_DB_PATH` | required | the SQLite file |
| `ADO_SIM_TOKEN_KEY` | required, ≥ 32 characters | key of the token HMAC (secret) |
| `ADO_SIM_PORT` | `8600` | |
| `ADO_SIM_SEED_FILE` | `seed/demo.yaml` | used by `reset` |
| `ADO_SIM_BUSY_TIMEOUT` | `30s` | lock wait for writers |
| `ADO_SIM_LOG_LEVEL` | `INFO` | |
| `ADO_SIM_OTLP_ENDPOINT` | unset | traces to Phoenix when set (project `ado-sim`) |

The simulator reads no `ADLC_*` setting (constitution VII).

## Seed file (`ado_sim/seed/demo.yaml`)

```yaml
organization: adlc-demo
project: Agentic ADLC
areas:                      # tree under the project root
  - Use cases
process:                    # Agile, with the Epic's states replaced by the terminal stages
  types:
    Epic:
      states:               # data only; never in code
        - {name: "T0 Intake", category: Proposed}
        - {name: "T1 Requirements", category: InProgress}
        # ... one per terminal stage ...
        - {name: "Closed", category: Completed}
        - {name: "Removed", category: Removed}
      fields: [Custom.AdlcUseCaseId, Custom.AdlcSubStage]
    Feature: {states: agile, fields: [Custom.AdlcRunId, Custom.AdlcDecision, Custom.AdlcComment]}
    User Story: {states: agile}
    Task: {states: agile, fields: [Custom.AdlcClarificationAnswer]}
    Bug: {states: agile}
  agile_states: [New, Active, Resolved, Closed, Removed]
  custom_fields:
    Custom.AdlcUseCaseId: {type: string}
    Custom.AdlcSubStage: {type: string}
    Custom.AdlcRunId: {type: string}
    Custom.AdlcDecision: {type: string}
    Custom.AdlcComment: {type: plainText}
    Custom.AdlcClarificationAnswer: {type: plainText}
identities:                 # no tokens here (FR-017)
  - {unique_name: adlc-platform@adlc.demo, display_name: ADLC Platform}
  - {unique_name: business.owner@adlc.demo, display_name: Business Owner}
  # ... one demo user per platform role used in the demo ...
```

Which type carries which run or clarification, and the allowed decision values, are set by the
platform's tracker mapping in feature 016; the seed only declares that the fields exist.
