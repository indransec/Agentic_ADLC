# Contract: File formats

## `adlc-specs/shared/roles.yaml` (role catalogue, TDS §3)

```yaml
schema_version: "1.0.0"
roles:
  - id: business_owner
    description: Use-case sponsor; owns value and terminate decision
  - id: product_owner
    description: Owns requirements, KPIs, backlog
  # … all 15 roles of TDS §3, in that order
```

- `id` values are unique and `snake_case`. Feature 002 adds the JSON Schema for this file and
  keeps this shape.

## Account file (path in `ADLC_ACCOUNTS_FILE`, outside the repo)

Example shipped as `deploy/accounts.example.yaml`:

```yaml
accounts:
  - account_name: owner.business
    display_name: Demo Business Owner
    roles: [business_owner]
    credential_hash: REPLACE_WITH_HASH   # run: uv run adlc-account hash
  - account_name: coe.lead
    display_name: Demo CoE Lead
    roles: [adlc_coe]
    credential_hash: REPLACE_WITH_HASH
```

- Unknown keys are refused. `roles` must be non-empty and in the catalogue. `account_name` is
  unique.
- `credential_hash` must start with `scrypt$`. Anything else is a placeholder: refused at
  startup in `demo`, and in `dev` the account loads but cannot sign in.
- Real account files live outside the repository, for example
  `~/.config/adlc/accounts.<env>.yaml`, and are mounted read-only into the API container.
