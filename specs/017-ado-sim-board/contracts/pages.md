# Contract: pages

All page routes are outside `/_apis/` and outside the OpenAPI document. Every one except
`/_signin`, `/_static/*` and `/health` needs a page session; without one, a full page answers
`303` to `/_signin?next=<path>` and an HTMX request answers `200` with `HX-Redirect: /_signin`.
Every `POST` needs the session's CSRF token (form field `csrf` or header `X-CSRF-Token`): else `403`.

| Method and path | Does |
| --- | --- |
| `GET /` | `303` to the board of the seeded organisation and project |
| `GET /_signin` | the sign-in form: a list of the seeded users (not the service account), a credential field |
| `POST /_signin` | `unique_name`, `credential`, `next`, pre-session CSRF; success: session cookie, `303` to `next` (only a local path) or the board; failure: the form again, `400`, one message |
| `POST /_signout` | revoke the session, clear the cookie, `303` to `/_signin` |
| `GET /{org}/{project}/_boards/board?area=<path>` | the board page (header with user and sign-out, area filter, create form, columns) |
| `GET /{org}/{project}/_boards/board/cards?area=<path>&open=<state>...` | the columns fragment (polled) |
| `POST /{org}/{project}/_boards/board/epics` | `title`, `description`, `area`: create an item of the board type as the signed-in user; success `303` to the board (HTMX: the refreshed columns); refusal: the form with the simulator's message beside the field, `400`, values kept |
| `GET /{org}/{project}/_workitems/edit/{id}` | the read-only item page (018 replaces it with the form); `404` page for an unknown item |
| `GET /_static/{file}` | `htmx.min.js`, `board.css`, the HTMX licence; cached for an hour |

An unknown organisation or project answers the `404` page (as the API, 015). Page responses carry
`Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and
`Cache-Control: no-store` (except static files).
