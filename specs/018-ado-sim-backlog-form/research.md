# Research: ADO Simulator Backlog and Work Item Form (018)

Decisions behind [plan.md](plan.md). Each: decision, rationale, alternatives.

## R-01 The form replaces 017's read-only page, at the same address

- **Decision**: `GET /{org}/{project}/_workitems/edit/{id}` renders the form; `POST` to the same
  address saves it. The form carries the revision it was opened at (hidden field) and the save calls
  `WorkItemStore.update` with `test /rev` first and one `add`/`remove` per changed field, as the
  signed-in identity. A `412` re-renders the form with the current item, the person's values kept
  and a conflict message (FR-004). Other refusals re-render with the message beside the field.
- **Rationale**: one path for every change (the store), so validation, history and attribution are
  the API's; the address is the one ADO and the platform's links use.

## R-02 Inputs by field type, values from the seed

- **Decision**: the field's type (015 `field.type`) and its allowed values (015
  `work_item_type_field.allowed_values`) choose the input: allowed values → a `<select>` (with an
  empty choice); `string` → text box; `plainText` and `html` → text area (HTML fields are edited as
  plain text and saved escaped in paragraphs, as 017's create form); `integer`/`double` → number;
  `dateTime` → `datetime-local`; `identity` → a select of the active seeded users (not the service
  account); `boolean` → a Yes/No select (an unticked checkbox is not sent, so clearing it could not
  be told from leaving it); `System.State` and area paths → selects; read-only system fields → text.
- **Rationale**: FR-003 from data the simulator already holds.

## R-03 The decision field's allowed values

- **Decision**: the seed's shared field list (`&adlc_fields`) declares `Custom.AdlcDecision` with
  `allowed_values` equal to the decision values of the platform's tracker mapping (Pass, Rework,
  Exception, Terminate, Approve waiver, Reject waiver, Complete escalation). A platform contract test
  reads both data files and fails when they differ (the platform still never imports the simulator).
- **Rationale**: the form offers a list (US1-2); one test keeps the two data files in step.
- **Alternatives**: the simulator reading the platform's mapping (forbidden: boundary).

## R-04 Form layout in the seed

- **Decision**: a `form` section in the seed: per type, ordered sections `{title, fields}`;
  validated (types and fields exist); stored as JSON in `board_setting` (key `form_layout`). Fields of
  the type not in the layout go to a last "Other fields" section; a type without a layout shows one
  section with every field.
- **Rationale**: FR-002 (data, not code); no schema change.

## R-05 Safe formatting of HTML fields (FR-005)

- **Decision**: an allow-list sanitiser in the simulator (`pages/sanitize.py`, standard-library
  `html.parser`): keeps `p`, `br`, `ul`, `ol`, `li`, `strong`, `b`, `em`, `i` and `a` with an
  `http(s)` `href` (rendered with `target="_blank" rel="noopener noreferrer"`); drops every other
  tag and every attribute; drops the content of `script`, `style`, `iframe`, `object`, `template`;
  escapes all text. Its output is the only string marked safe in any template.
- **Rationale**: no new dependency; the subset the platform writes (016 desired descriptions) is
  small. Property-tested with hostile inputs (SC-004).
- **Alternatives**: `nh3` (MIT, a compiled extension: a new binary dependency for a small need);
  `bleach` (deprecated).

## R-06 History

- **Decision**: from `WorkItemStore.updates`: each update's changer, change time and every changed
  field except `System.Rev`, `System.ChangedDate` and `System.ChangedBy` (shown once per update) with
  old and new values as text; values over 200 characters shortened with a `<details>` holding the
  full value; link updates name the linked item. Newest first.

## R-07 Comments

- **Decision**: `POST /{org}/{project}/_workitems/edit/{id}/comments` with `text` calls
  `comments.add_comment` as the signed-in identity (so the item's revision and history follow, as
  015); the list is `list_comments(order="desc")`.

## R-08 Backlog tree

- **Decision**: one read of every item (id, type, title, state, area) and every hierarchy link;
  roots are items of the board type without a parent (in the area filter); the tree is built in
  Python, children by id, any depth; rows are nested lists with `<details>` per item that has
  children (open by default; the levels a person closed are kept across the refresh, `hx-include`
  of the closed set, the board's mechanism the other way round);
  `GET .../_backlogs/backlog` and `.../_backlogs/backlog/rows` (the polled fragment).
- **Rationale**: 600 items is well within one query (SC-002).

## R-09 Navigation and links

- **Decision**: the base template gains a navigation bar (Board, Backlog) for signed-in pages; the
  form links to the item's parent and children; field values that are `http(s)` addresses become
  links opening in a new tab without referrer or opener (FR-006).

## R-10 Accessibility

- **Decision**: the 017 static checker over the form (normal, conflict and error states) and the
  backlog; errors use `role="alert"` and `aria-describedby` on their field (FR-013).

## Dependencies and licences

No new dependency (Jinja2, python-multipart and HTMX from 017).
