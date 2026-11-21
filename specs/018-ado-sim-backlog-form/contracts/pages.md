# Contract: pages (additions to 017)

017's rules apply: a page session for every route, CSRF on every POST, security headers, values
escaped, page routes outside the OpenAPI document.

| Method and path | Does |
| --- | --- |
| `GET /{org}/{project}/_workitems/edit/{id}` | the work item form (replaces 017's read-only page) |
| `POST /{org}/{project}/_workitems/edit/{id}` | `rev`, `csrf` and the form's fields: save the changed fields as the signed-in user with `test /rev`; success `303` back to the form; `412` the form with the current item, the person's values and a conflict message; `400` the form with the message beside the field |
| `POST /{org}/{project}/_workitems/edit/{id}/comments` | `text`, `csrf`: add a comment as the signed-in user; `303` back to the form (`#comments`) |
| `GET /{org}/{project}/_backlogs/backlog?area=<path>` | the backlog tree |
| `GET /{org}/{project}/_backlogs/backlog/rows?area=&closed=<id>...` | the tree fragment (polled at the board's interval); the tree starts open, so the levels a person closed travel with each poll |

Every page shows a navigation bar: Board, Backlog.
