# Contract: IdentityProvider interface

Callers (API dependencies now; the inbox in 007 and the approval API later) depend only on this
interface (constitution VII, FR-017). `LocalIdentityProvider` implements it for the MVP; an
`OidcIdentityProvider` can replace it later through configuration and one adapter.

```text
Person            = { account_name: str, display_name: str, roles: frozenset[str] }
SessionGrant      = { token: str, expires_at: datetime (UTC), person: Person }

IdentityProvider (Protocol)
  sign_in(account_name: str, password: SecretStr) -> SessionGrant
      raises InvalidCredentials  (same type for unknown account, wrong password, placeholder)
  current_person(token: str) -> Person
      raises NotAuthenticated     (missing, malformed, bad signature, expired, revoked)
  roles(account_name: str) -> frozenset[str]
      raises UnknownAccount
  sign_out(token: str) -> None
      idempotent; an already invalid token is not an error
```

## Behaviour rules

- `roles()` and `current_person()` read the current account file data, so role changes apply
  on the next call after the file is reloaded at startup. Hot reload is not in scope.
- Every `sign_in` call logs `auth.sign_in` at INFO with `account_name`, `outcome` (`success` or
  `refused`) and time. The password, hash and token are never logged (FR-020).
- Role ids returned are always members of the role catalogue. The provider never invents or
  hard-codes roles (FR-019).
- Implementations must not do network calls on the request path in the local variant.

## Errors to HTTP (API layer)

| Exception | HTTP | Body |
| --- | --- | --- |
| `InvalidCredentials` | 401 | `{"detail": "invalid credentials"}` |
| `NotAuthenticated` | 401 | `{"detail": "not authenticated"}` |
| `UnknownAccount` (account removed after sign-in) | 401 | `{"detail": "not authenticated"}` |
