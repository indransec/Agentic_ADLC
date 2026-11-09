# Data Model: Platform Foundation (001)

This feature creates the database layout and the minimum baseline needed to prove the
migration path and the ledger rule (FR-009). Runtime, spec-registry and event tables arrive in
features 002, 003 and 005. Names follow SA Annex A.6.

## Database identities

| Identity | Created by | Used by | Rights |
| --- | --- | --- | --- |
| `POSTGRES_USER` (superuser) | PostgreSQL image | Init script only | Infrastructure only; never configured in any platform service |
| `adlc_owner` | `deploy/postgres/init/01-roles.sh` | `migrate` service, `make migrate*`, migration-check | Owns database `adlc`, the four schemas and all objects; still refused UPDATE/DELETE/TRUNCATE on ledger rows by trigger |
| `adlc_app` | same script | `api` and every later runtime service | `CONNECT` on `adlc`; `USAGE` on the four schemas; per-table grants from migrations only |

## Schemas (FR-006)

| Schema | Owner concern (SA §10) | Tables in 001 | Filled by |
| --- | --- | --- | --- |
| `spec` | Spec registry and projections | none | 002 |
| `run` | Use cases, runs, activity, sign-offs | none | 003, 005, 007 |
| `ledger` | Append-only evidence | `ledger_record` (baseline) | extended in 005 |
| `events` | Outbox and idempotency | none | 003 |

## Table `ledger.ledger_record` (baseline)

| Column | Type | Null | Rule |
| --- | --- | --- | --- |
| `ledger_record_id` | bigint identity | no | Primary key |
| `ledger_key` | text | no | Unique; Annex A.2 form `<usecase_id>/T<n>/<run_version>` (format check arrives in 005; not validated here so no terminal pattern is hard-coded) |
| `content_hash` | text | no | `CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$')` (Annex A.5) |
| `previous_record_hash` | text | yes | Same check when not null; null only for the first record of a use case |
| `written_at` | timestamptz | no | Default `now()` |

**Privileges**: `adlc_app`: `SELECT, INSERT` only, plus `USAGE` on the identity sequence.

**Immutability (FR-011, clarification 1)**:

- Function `ledger.reject_mutation()` raises `ledger.ledger_record is append-only:
  <TG_OP> refused`, with SQLSTATE `42501` (insufficient_privilege).
- Trigger `ledger_record_no_update_delete`: `BEFORE UPDATE OR DELETE ON ledger.ledger_record
  FOR EACH ROW`.
- Trigger `ledger_record_no_truncate`: `BEFORE TRUNCATE ON ledger.ledger_record FOR EACH
  STATEMENT`.
- Both triggers fire for every identity, including `adlc_owner`. Only `DROP TABLE` in the
  downgrade or reset removes ledger data.

## Migration `0001_baseline`

- **Upgrade**: create the four schemas (owned by `adlc_owner`); grant `USAGE` to `adlc_app`;
  create `ledger.ledger_record`, the function and both triggers; grant the table privileges.
- **Downgrade**: drop the triggers, function and table, then the four schemas (`RESTRICT`, so
  a downgrade never silently drops objects created outside migrations).
- Alembic's version table lives in schema `public` as `alembic_version` (tool-owned, outside
  the four platform schemas).

## Non-database entities

### Settings (FR-013 to FR-015)

A typed model; every field, its form and whether it is secret are in
[contracts/settings.md](contracts/settings.md). Validation rules:

- Required settings without a value stop startup (exit code 2), one line per problem, naming
  the variable.
- Secret fields are never printed (not in errors, logs, `/health` or traces).
- `ADLC_ENV` ∈ {`dev`, `demo`}.

### Role (role catalogue)

| Field | Rule |
| --- | --- |
| `id` | `snake_case`, unique, Annex A.4 `<function>_<title>` form or the single-word exceptions in TDS §3 (`sre`, `adlc_coe`) |
| `description` | Non-empty text |

Source: `adlc-specs/shared/roles.yaml` (15 entries from TDS §3). Read-only at runtime.

### Local account

| Field | Rule |
| --- | --- |
| `account_name` | Unique; `^[a-z][a-z0-9._-]{1,39}$` |
| `display_name` | Non-empty |
| `roles` | Non-empty list; each must be a role `id` in the catalogue |
| `credential_hash` | `scrypt$…` encoded hash; anything else is a placeholder, which is refused in `demo` and refused for sign-in in `dev` |

Source: the file at `ADLC_ACCOUNTS_FILE` (outside the repository). The format is in
[contracts/files.md](contracts/files.md).

### Session

| Field | Rule |
| --- | --- |
| `account_name` | Signed into the token |
| `session_id` | Random 128-bit id, signed into the token |
| issued time | Carried by the signer; the token is refused after `ADLC_SESSION_TTL` |
| revoked | In-process set, filled on sign-out, entries dropped after expiry (research R-05) |

State transitions: `issued → active → (expired | revoked)`; both end states are final and
refused by the auth dependency.
