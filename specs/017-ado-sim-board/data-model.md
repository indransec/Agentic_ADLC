# Data Model: ADO Simulator Board (017)

A new simulator migration `ado_sim/src/ado_sim/migrations/0002_pages.sql`; times are ISO 8601 UTC
text with microseconds, as in 015.

## Tables

**`page_password`**: one row per identity that has a page password (FR-002 option 1).

| Column | Type | Notes |
| --- | --- | --- |
| identity_id | text PK | FK `identity`; never the service account |
| password_hash | text | `scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>` |
| set_at | text | |

Cleared by deleting the row (`ado-sim password clear`).

**`page_session`**: one row per sign-in (FR-003).

| Column | Type | Notes |
| --- | --- | --- |
| session_hash | text PK | SHA-256 of the cookie's random session id; the id itself is never stored |
| identity_id | text | FK `identity` |
| csrf_token | text | random, per session (FR-004) |
| created_at, expires_at | text | expiry = created + `ADO_SIM_PAGE_SESSION_TTL` (absolute, not extended by use) |
| revoked_at | text NULL | set by sign-out, and for all the user's sessions when their page password is cleared or a token revoked (FR-004a) |

Expired and revoked rows are removed by `ado-sim migrate` and at start (housekeeping), never read
as valid.

## Seed additions (data, validated)

```yaml
identities:
  - {unique_name: adlc-platform@adlc.demo, display_name: ADLC Platform, service: true}
board:
  type: Epic                       # a work item type of the process
  card_fields: [Custom.AdlcSubStage]   # fields of that type shown on cards
  collapsed_states: [Closed, Removed]  # states of that type whose columns start collapsed
  refresh: 5s                      # 2s..60s
```

At most one identity is `service: true`. Without a `board` section the pages show a message that
the board is not configured.

## Settings (additions)

| Name | Default | Notes |
| --- | --- | --- |
| `ADO_SIM_PAGE_SESSION_TTL` | `8h` | page session lifetime |
| `ADO_SIM_DEMO_PASSWORD` | unset | the shared demo password (FR-002 option 2); at least 12 characters; a warning is logged at start when set |
| `ADO_SIM_SECURE_COOKIES` | `false` | set `Secure` on cookies (true behind https) |

## View models (no tables)

- **Column**: state name, collapsed flag, cards, count.
- **Card**: id, title, card field values (label and text), last changer's display name.
- **Item page**: id, type, state, title, area, every field with a value (as text), parent and
  children (id, type, title), updates (who, when, changed fields), comments (who, when, text).
