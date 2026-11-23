# adlc.web

The ui process (feature 022; specs/022-react-web-app/contracts/web-server.md). It serves the built
browser application (`web/`, built into `web/dist` by `make web-build`) and forwards `/api` to the
platform API. Python only: Node is needed to build the application, never to run it.

Started with `adlc-web` (`--host`, default `127.0.0.1`; compose uses `0.0.0.0`).

## Settings (`UiSettings`, environment only)

| Variable | Default | Use |
| --- | --- | --- |
| `ADLC_API_URL` | `http://api:8000` | Where `/api/*` goes |
| `ADLC_UI_PORT` | `8501` | Listening port |
| `ADLC_UI_DIST_DIR` | `web/dist` | The built application |
| `ADLC_UI_DASHBOARD_REFRESH` | `10s` | Sent to the page in `/config.json` |
| `ADLC_ENV` | unset | Sent to the page in `/config.json` (the environment badge) |

## Paths

| Path | Answer |
| --- | --- |
| `/api/{path}` | Forwarded to `{ADLC_API_URL}/{path}` with the same method, query and streamed body. Request headers come from an allowlist (`cookie`, `content-type`, `content-length`, `accept`, `x-adlc-csrf`), plus `x-forwarded-proto` and `x-forwarded-host`. Answer headers come from an allowlist (`set-cookie`, `content-type`, `content-disposition`, `cache-control`, `content-length`, `x-content-type-options`). If the API is unreachable: `502 {"kind": "unavailable", ...}`. |
| `/config.json` | `{"env", "dashboard_refresh_seconds"}`, `no-store` |
| `/health` | `200 {"status": "ok"}`, or `503 {"status": "missing build"}` |
| `/assets/*` | Built files, cached for a year (hashed names); 404 if missing |
| any other GET | `index.html`, `no-cache` (the application's own routes) |

## Rules

- **Security headers.** Every answer carries a strict CSP (`script-src 'self'`, no `unsafe-eval`,
  `frame-ancestors 'none'`), plus `nosniff`, `Referrer-Policy: same-origin` and
  `Cross-Origin-Opener-Policy: same-origin`.
- **No CORS.** No CORS header is ever sent; any from the API is dropped.
- **Platform untouched.** The platform's paths, its public paths (`PUBLIC_PATHS`) and its sessions
  are unchanged. This process holds no session and no secret.
- **Logs.** Method, path and status only, never the query, headers or bodies. uvicorn's access log
  is off.
- **Boundary.** It imports only `adlc.web` and `adlc.config` from the platform
  (`tests/unit/test_ui_boundary.py`).
