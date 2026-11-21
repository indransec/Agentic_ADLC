# Research: ADO Simulator Board (017)

Decisions behind [plan.md](plan.md). Each: decision, rationale, alternatives.

## R-01 Pages in the simulator's own app, at ADO's addresses

- **Decision**: page routes are added to the simulator's FastAPI app, at the addresses ADO uses and
  that 015's `_links.html` already points to: `/{organization}/{project}/_boards/board` (the board)
  and `/{organization}/{project}/_workitems/edit/{id}` (an item); sign-in at `/_signin` and
  `/_signout`; assets at `/_static/`. Page routes are left out of the OpenAPI document
  (`include_in_schema=False`), so the published REST contract of 015 is unchanged; 015's test that
  "documented paths equal the routes" compares against the routes in the schema only.
- **Rationale**: one process, one port, the same data and history code; links the platform already
  writes resolve to a real page.
- **Alternatives**: a second app or process (two ports, shared database code); a separate front end
  (a build step, against the decision for server-rendered pages).

## R-02 Server-side sessions, not signed cookies

- **Decision**: signing in creates a random 32-byte session id; the cookie holds it
  (`HttpOnly`, `SameSite=Lax`, `Secure` when served over https, path `/`); the database keeps only
  its SHA-256 hash with the identity, the expiry (`ADO_SIM_PAGE_SESSION_TTL`, default 8h) and a CSRF
  token. Sign-out sets `revoked_at`. No signing library.
- **Rationale**: revocation (sign-out in another tab, FR-003) is a row update; nothing to sign means
  no extra key setting; the token-hash pattern is the one 015 uses for access tokens. A restart keeps
  sessions (they are in the database).
- **Alternatives**: `itsdangerous` signed cookies (a new dependency in the simulator, a key, and
  revocation still needs a table); Starlette's `SessionMiddleware` (needs itsdangerous; stores data
  client-side).

## R-03 Three credentials, one check (FR-002)

- **Decision**: the seed marks the platform's service account (`service: true` on its identity;
  at most one); it is never offered on the sign-in page and never signed in. `pages/signin.py`
  checks, for the chosen user: (1) the page password hash (scrypt, as the platform's account
  hashes: `hashlib.scrypt`, n=2^15, r=8, p=1, 16-byte salt, stored as `scrypt$n$r$p$salt$hash`);
  (2) `ADO_SIM_DEMO_PASSWORD` when set (constant-time compare); (3) the user's active tokens (the
  token's hash, as `auth.authenticate`). Any match signs in the chosen user; every failure returns
  the same message after the same work (a dummy scrypt when the user has no password), so timing
  does not tell which part failed.
- **Rationale**: the 2026-11-21 answer (all three); scrypt is in the standard library and already
  the platform's choice.
- **Alternatives**: argon2 (a new dependency); bcrypt (a new dependency, 72-byte limit).

## R-04 CSRF

- **Decision**: a per-session token, rendered as a hidden field in every page form and sent as an
  `X-CSRF-Token` header by HTMX (`hx-headers` on `<body>`); every page POST compares it in constant
  time. `SameSite=Lax` is the second layer. The sign-in form, which has no session yet, uses a
  short-lived pre-session token in its own cookie (double-submit).
- **Rationale**: FR-004 with no dependency.

## R-05 Templates, HTMX and styles

- **Decision**: Jinja2 3.1.6 templates under `ado_sim/src/ado_sim/pages/templates/` with
  autoescaping on for every template (FR-012); HTMX 2.0.4 (`htmx.min.js`, Zero-Clause BSD) and one
  hand-written stylesheet under `ado_sim/src/ado_sim/pages/static/`, served by the simulator
  (FR-014); `python-multipart` 0.0.32 for form posts. No CDN, no JavaScript beyond HTMX.
- **Rationale**: the decided stack (2026-11-20); both libraries are already in the platform's lock
  with permissive licences; vendoring keeps the demo offline.

## R-06 Board data

- **Decision**: `pages/board.py` reads, in one read transaction: the board type's states in process
  order (seed), and every work item of that type under the chosen area (the `work_item` table's
  `type_name`, `state`, `area_path` indexes) with its title, card fields and last changer; cards
  are grouped by state, states not in the process go to an "other" column. Creating an Epic calls
  `WorkItemStore.create` with the signed-in identity, so validation, history and attribution are
  the API's.
- **Rationale**: one query for 200 items is well inside SC-001; reusing the store keeps one path
  for every change (SC-003).
- **Alternatives**: WIQL through the API (an HTTP hop inside one process).

## R-07 Refresh

- **Decision**: the columns are one fragment (`GET .../_boards/board/cards?area=`), polled by HTMX
  every `board.refresh` seconds and swapped into the columns' container only, so the page, its
  scroll position and the filter (in the address) stay. Collapsed columns are `<details>` elements
  whose open state is sent back with each poll (`hx-include`) and rendered the same way. A failed
  refresh shows a "not current" banner (HTMX's error events); the next success removes it. An
  expired session answers the fragment with `HX-Redirect` to the sign-in page.
- **Rationale**: FR-008 with plain polling; no server push to keep up.

## R-08 Board settings in the seed

- **Decision**: the seed file gains a `board` section: `type` (a work item type), `card_fields`
  (field references, existing on that type), `collapsed_states` (states of that type), `refresh`
  (`<int>s`, 2-60). Seed validation refuses anything that does not exist. The demo seed: type
  `Epic`, card field `Custom.AdlcSubStage`, collapsed `Closed` and `Removed`, refresh `5s`.
- **Rationale**: FR-005 (data, not code); the simulator still attaches no meaning to the names.

## R-09 Accessibility checks

- **Decision**: no browser in the test run. A static checker (`tests/pages/a11y.py`, standard-library
  `html.parser`) asserts on every page: `<html lang>`, one `<main>`, `<header>` and `<nav>`
  landmarks, one `<h1>`, an `<h2>` per column, a label for every input, a name for every button and
  link, no positive `tabindex`, visible focus styles present in the stylesheet. SC-005 is measured
  with it; a browser-based check (axe) is noted as a follow-up for 018's richer form.
- **Rationale**: keeps the simulator's dependencies light (no Playwright or Node).

## R-10 Operator command

- **Decision**: `ado-sim password set <unique-name>` (reads the password twice without echo) and
  `ado-sim password set --all` (one password for every demo user, for rehearsals; still hashed per
  user); `ado-sim password clear <unique-name>`. Exit codes as 015 (0, 1 refused, 2 invalid).
- **Rationale**: FR-002 option 1.

## Dependencies and licences

| Dependency | Version | Licence | Use |
| --- | --- | --- | --- |
| jinja2 (with markupsafe) | 3.1.6 (3.0.4) | BSD-3-Clause | templates |
| python-multipart | 0.0.32 | Apache-2.0 | form posts |
| htmx (vendored file) | 2.0.4 | 0BSD | board refresh |

All except the vendored HTMX file are already locked in the platform; HTMX's licence text is kept
next to the file.
