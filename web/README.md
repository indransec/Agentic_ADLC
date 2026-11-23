# web

The browser application (feature 022; `specs/022-react-web-app/`). React and TypeScript (strict),
built by Vite into `web/dist`. `adlc-web` (`src/adlc/web/`, Python) serves it and forwards `/api`
to the platform API. Node is needed to build and check it, never to run the platform.

## Commands (from the repository root)

| Command | What it does |
| --- | --- |
| `make web-install` | `corepack enable`, `pnpm install --frozen-lockfile` (part of `make install`) |
| `make web-browsers` | Playwright's Chromium, with system libraries (CI, first setup) |
| `make web-build` | `web/dist` (part of `make local-setup`) |
| `make web-dev` | Vite on :5173, forwarding `/api` and `/config.json` to `adlc-web` on `ADLC_UI_PORT` |
| `make web-check` | lint and format, type check and contract freshness, component tests, end-to-end tests (part of `make check`) |
| `make openapi` | Re-export the platform's OpenAPI document and regenerate `src/api/schema.d.ts` |
| `E2E_ALL_BROWSERS=1 pnpm -C web exec playwright test --project firefox` (or `webkit`) | The end-to-end suite in Firefox or WebKit (Safari's engine); each run starts its own stack |

Versions are pinned exactly in `package.json`, with `pnpm-lock.yaml` committed. pnpm refuses
packages younger than its minimum release age, so a just-published version is pinned below it.

## Layout

```text
src/
  api/       client.ts (the only module that reaches the network), errors.ts, queries.ts,
             openapi.json and schema.d.ts (generated: make openapi)
  auth/      session context, sign-in page, session guard
  nav/       registry.ts (every page), sidebar, navigate()
  pages/     one folder per page; pages/index.ts registers each, loaded on first use
  ui/        Literal, StatusBadge, DataTable, Tabs, Plot, Metric, format and status helpers, theme.css
  test/      typed fixtures (from the API's golden answers), MSW handlers, render helpers
e2e/         Playwright specs and fixtures; the stack is tests/e2e/stack.py
```

## The page registry

`src/nav/registry.ts` lists every page: id, title, section, path, icon, sidebar visibility and the
query parameters it keeps in the address. The router, the sidebar and `navigate()` are built
from it. Ids travel as query parameters, because run ids contain "/". A later mode (the 019
console) would add a field and filter this table.

## Rules, and how they are enforced

| Rule | Enforced by |
| --- | --- |
| Text written by agents or people is literal text, never markup, never in a label | `<Literal>` and `DataTable`; ESLint bans `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML` and `insertAdjacentHTML`; chart text goes through `plotText()`; the rendering e2e test |
| Only `src/api/client.ts` reaches the network | ESLint `no-restricted-globals` (`fetch`, `XMLHttpRequest`) and `no-restricted-imports` (`openapi-fetch` outside `src/api/`); `src/lint-guard.test.ts` proves the rules fire |
| The session is never visible to the page | HttpOnly cookie; the CSRF value is held in memory only; the session e2e test |
| No terminal, control, role, outcome or threshold value in code | The decision form is built from `run.form`; who may see dead letters is the platform's answer (403) |
| Every run action sends the version the person saw | The run is not refreshed in the background; a stale answer reloads it with a message |
| Strict CSP | Served by `adlc-web`; the e2e console guard fails on any violation |
| Accessible | jsx-a11y lint rules; axe on every page and a keyboard-only flow in e2e |

## Naming

File and folder names are kebab-case (constitution XIII, SA Annex A.1), enforced by
`unicorn/filename-case`. Component identifiers inside the code are PascalCase.
