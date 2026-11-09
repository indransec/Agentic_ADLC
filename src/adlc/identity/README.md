# adlc.identity

Who is signed in, and which catalogue roles they hold (feature 001; contracts/identity-provider.md).

- `IdentityProvider` (Protocol): `sign_in`, `current_person`, `roles`, `sign_out`. Callers depend only on this, so an OIDC adapter can replace `LocalIdentityProvider` later.
- `LocalIdentityProvider`: accounts from `ADLC_ACCOUNTS_FILE` (outside the repo), roles validated against `ADLC_ROLE_CATALOGUE` (`adlc-specs/shared/roles.yaml`). No role names appear in code.
- `hashing`: stdlib scrypt, encoded `scrypt$n$r$p$salt$hash`. Any other value is a placeholder and never signs in. In `demo`, a placeholder stops startup.
- `sessions`: signed tokens (itsdangerous) that expire after `ADLC_SESSION_TTL`. Sign-out revocations are kept in memory, so they are lost on API restart (accepted MVP limit).

Sign-in attempts are logged as `auth.sign_in account_name=... outcome=success|refused`; passwords, hashes and tokens are never logged. There is no lockout in the MVP.
