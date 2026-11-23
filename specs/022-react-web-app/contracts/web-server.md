# Contract: The ui process (`adlc.web`, console script `adlc-web`)

A Starlette application under uvicorn, listening on `ADLC_UI_PORT`. Research R-03, R-11 to R-14.

## Settings (`UiSettings`, environment only)

| Variable | Default | Use |
| --- | --- | --- |
| `ADLC_API_URL` | `http://api:8000` | Where `/api/*` is forwarded (existing) |
| `ADLC_UI_PORT` | `8501` | Listening port (existing) |
| `ADLC_UI_DASHBOARD_REFRESH` | `10s` | Sent in `/config.json` (existing) |
| `ADLC_ENV` | unset | Sent in `/config.json` (existing) |
| `ADLC_UI_DIST_DIR` | `web/dist` | Built files (new) |

Listening address: `0.0.0.0` in containers; `127.0.0.1` in `deploy/Procfile.local`. Set by a CLI
flag, as for the API.

## Paths

| Method, path | Behaviour |
| --- | --- |
| any `/api/{path}` | Forward to `{ADLC_API_URL}/{path}?{query}` with the same method and a streamed body. Request headers come from an allowlist (`cookie`, `content-type`, `content-length`, `accept`, `x-adlc-csrf`), and the proxy adds `x-forwarded-proto` and `x-forwarded-host`. Response status is passed through, with response headers from an allowlist (`set-cookie`, `content-type`, `content-disposition`, `cache-control`, `content-length`, `x-content-type-options`) and a streamed body. API unreachable or timed out: `502 {"kind": "unavailable", "detail": "the platform could not be reached"}`. |
| `GET /config.json` | `{"env": …, "dashboard_refresh_seconds": …}`, `Cache-Control: no-store` |
| `GET /health` | `200 {"status": "ok"}` when `index.html` exists in the dist folder; otherwise `503 {"status": "missing build"}` |
| `GET /assets/{file}` | File from the dist folder; `Cache-Control: public, max-age=31536000, immutable`; 404 if missing (no fallback) |
| `GET` any other path | `index.html`, `Cache-Control: no-cache` (client-side routes) |
| non-GET on a non-`/api` path | 405 |

## Headers on every answer (research R-11)

```text
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none';
  frame-ancestors 'none'; form-action 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
Cross-Origin-Opener-Policy: same-origin
```

## Rules

- No CORS headers are ever sent.
- Logs record method, path (without query) and status only. Never headers, cookies or bodies.
- Imports: only `adlc.web` and `adlc.config` from the platform (boundary test).
- Path traversal outside the dist folder is refused (404).

## Tests

`tests/integration/web/test_server.py`, using a stub API built with Starlette's test client:

- **Proxy:** method, path, query and body are forwarded; request headers outside the allowlist
  (for example `authorization` and `x-foo`) are dropped; `set-cookie` and `content-disposition`
  are passed back; an upload streams; the API being down answers 502 in the error shape.
- **Serving:** the SPA fallback serves `index.html`; asset cache headers are set; a missing asset
  answers 404; traversal is refused.
- **Settings and health:** `/config.json` reflects the settings; `/health` reports a missing
  build.
- **Headers:** CSP and the other headers are on every answer.
