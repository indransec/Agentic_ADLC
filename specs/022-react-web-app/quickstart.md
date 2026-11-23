# Quickstart: Web Application Rebuild (feature 022)

How to show that the feature works. Contracts: [session](contracts/session.md),
[web server](contracts/web-server.md), [platform contract](contracts/platform-contract.md),
[pages](contracts/pages.md), [parity](contracts/parity.md).

## Prerequisites

- What `docs/run-without-docker.md` already lists: uv, Python 3.12, git.
- **New:** Node.js 24 LTS, then `corepack enable`, which provides the pnpm version pinned in
  `web/package.json`.
- `.env` filled in from `.env.example` (no new required values; `ADLC_UI_DIST_DIR` defaults to
  `web/dist`).

## 1. Install and build

```sh
make install          # uv sync --locked, plus pnpm install --frozen-lockfile in web/
make web-build        # web/dist/index.html and hashed assets
```

## 2. Checks

```sh
make check            # lint, typecheck, spec-validate, test, pilot-check, and web-check
make web-check        # web only: web-lint, web-typecheck (incl. schema freshness), web-test, web-e2e
```

Expected: all pass.

**Drift check (SC-008).** Rename a field in one answer model and run `make test`:
`test_openapi_fresh` fails. Run `make openapi`, then `make web-typecheck`: the pages reading the
old name fail to compile.

## 3. Run locally (no containers)

```sh
make local
```

- Open `http://127.0.0.1:8501` and sign in with an account from `ADLC_ACCOUNTS_FILE`. The Inbox
  opens.
- **Session (SC-003):** in the browser's developer tools, Application → Cookies shows
  `adlc_session` marked HttpOnly and SameSite Strict. `document.cookie` in the console does not
  contain it. Local and session storage are empty of tokens.
- **Deep link:** sign out, then open `http://127.0.0.1:8501/?run=<a run id>`. Sign-in appears,
  then the Run page opens on that run.
- **Side-by-side period only:** Streamlit is on `http://127.0.0.1:8502` (`ADLC_LEGACY_UI_PORT`).

## 4. Cross-site refusal (SC-004)

While signed in, from another origin (for example a local file served on another port), submit a
form that POSTs to `http://127.0.0.1:8501/api/usecases`. The answer is 403, the cookie is not
sent (SameSite) or the CSRF header is missing, and no use case is created.

Automated in `tests/integration/api/test_csrf.py` and `web/e2e/session.spec.ts`.

## 5. Demo walk (SC-001)

Reset the demo data (`make demo-reset`), then follow the Phase 1 demo
script (`demo/`) D-1 to D-9 entirely in the rebuilt application:

| Demo moment | Where |
| --- | --- |
| D-1, D-2, D-3 | Inbox → Run → Decision (rework with comment and root cause) |
| D-4 | Escalation |
| D-5 | Waiver |
| D-6 | Run → Evidence; Use cases → Verify |
| D-7 | Inbox → Proposed events and change requests |
| D-8 | Journey, Activity, Portfolio (auto refresh) |
| D-9 | Clarification |

Expected: no step needs the old application.

## 6. Containers

```sh
make up
```

- The `ui` service is healthy (`/health`).
- `http://localhost:${ADLC_UI_PORT:-8501}` serves the application.
- `docker compose exec ui which node` finds nothing (no Node at runtime).

## 7. Cutover (end of feature)

- With every row in [parity.md](contracts/parity.md) passing, the cutover commit removes
  Streamlit (research R-14).
- After it, `uv tree | grep -E 'streamlit|plotly'` is empty and `ls src/adlc/ui` fails.
- `make check` and the demo walk pass again.
