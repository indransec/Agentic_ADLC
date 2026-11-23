# Contract: Browser session and cross-site protection (platform API)

The changes to `adlc.api.auth` and `adlc.api.routes.auth`. Everything not listed here is unchanged.
Research R-01 and R-02 explain the choices.

## `POST /auth/sign-in` (public, as today)

Request body: today's fields plus an optional one.

```json
{"account_name": "string", "password": "string", "session": "bearer" | "cookie"}
```

`session` defaults to `"bearer"`, which gives today's request and answer exactly (FR-015).

| Case | Status | Body | Cookie |
| --- | --- | --- | --- |
| Bearer, valid | 200 | `{"token", "token_type": "bearer", "expires_at", "person"}` | none |
| Cookie, valid, header `X-ADLC-CSRF: sign-in` | 200 | `{"expires_at", "person", "csrf_token"}` (no `token`) | `adlc_session=<token>; HttpOnly; SameSite=Strict; Path=/; Max-Age=<n>[; Secure]` |
| Cookie, header missing or wrong | 403 | `{"kind": "not_allowed", "detail": "cross-site request refused"}` | none |
| Wrong account or password (either mode) | 401 | `{"kind": "not_signed_in", "detail": "invalid credentials"}` | none |

`Secure` is set when the original scheme is https: the request URL scheme, or `X-Forwarded-Proto`
set by the ui process.

## Authentication middleware (every non-public path)

1. If `Authorization: Bearer <token>` is present, use it (today's behaviour). No CSRF check.
2. Otherwise, if the cookie `adlc_session` is present, use it. If the method is not GET, HEAD or
   OPTIONS, require `X-ADLC-CSRF` to equal the HMAC value for this token. A mismatch answers
   `403 not_allowed`, "cross-site request refused".
3. Otherwise answer `401 not_signed_in` (as today).

`request.state.token` and `request.state.person` are set as today, whichever way the session
arrived. `PUBLIC_PATHS` stays `{"/health", "/auth/sign-in"}`.

## `GET /auth/me`

Today's `PersonOut`, plus `csrf_token` (string) only when the session came from the cookie.
Bearer answers are unchanged.

## `POST /auth/sign-out`

Revokes the token (as today). When the session came from the cookie, the answer also clears it:
`adlc_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict`. It needs the CSRF header like any
other cookie-authenticated change.

## Tests (written first)

`tests/integration/api/test_cookie_session.py` and `tests/integration/api/test_csrf.py`:

- **Sign-in:** bearer sign-in is unchanged; cookie sign-in sets the attributes above and leaves
  the token out of the body; the token never appears in any answer body in cookie mode; `Secure`
  follows the scheme.
- **Reads:** GET with the cookie works; GET with neither cookie nor bearer answers 401; an
  expired or revoked cookie answers 401.
- **CSRF:** a POST with the cookie and no CSRF header answers 403, and so does one with a wrong
  value or another session's value. A POST with a bearer token and no CSRF header works.
- **Sign-in CSRF:** cookie-mode sign-in without `X-ADLC-CSRF: sign-in` answers 403.
- **Sign-out** clears the cookie, and the same cookie then answers 401.
- **Public paths:** the set is unchanged (the existing deny-by-default test still passes).
