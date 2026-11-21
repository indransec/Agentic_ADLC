# Implementation Plan: ADO Simulator Backlog and Work Item Form

**Branch**: `018-ado-sim-backlog-form` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-ado-sim-backlog-form/spec.md` (Gate 1 approved
2026-11-21)

## Summary

The simulator's read-only item page (017) becomes a work item form: sections from the seed's form
layout, inputs chosen by field type and allowed values (the decision field is a list), a save that
sends only the changed fields with `test /rev` as the signed-in user and keeps the person's values on
a conflict, comments, a history with old and new values, and links (the run's evidence opens the
platform's console). A backlog page shows each Epic with its descendants as a collapsible tree,
filtered by area and refreshed like the board. HTML fields are shown through an allow-list sanitiser.
No platform code changes, except one platform contract test that keeps the seed's decision values and
the tracker mapping's in step.

## Technical Context

**Language/Version**: Python 3.12, the `ado_sim/` uv project (as 015 and 017).

**Primary Dependencies**: as 017 (FastAPI, Jinja2, python-multipart, HTMX); no new dependency.

**Storage**: no new table; seed additions (form layout, the decision field's allowed values) in
`board_setting` and 015's `work_item_type_field` ([data-model.md](data-model.md)).

**Testing**:
- **Unit (test first)**: the sanitiser (allow-list, dropped content, links, hostile inputs as a
  hypothesis property); form layout validation; field inputs by type; changed-field diffing into
  patch operations; history entries; the backlog tree.
- **Pages**: the form (every input kind, save, conflict, refusals with values kept, comments,
  history, links), the backlog (tree, collapse kept on refresh, filter), the route sweep and CSRF
  (017's tests cover new routes automatically), static accessibility checks of every state.
- **Properties**: backlog with 600 items and the form's open time (SC-002); concurrent saves
  (SC-003); hostile values on every page (SC-004).
- **Platform contract**: the seed's decision allowed values equal the tracker mapping's values.

**Target Platform / Project Type / Constraints**: as 017.

**Performance Goals**: backlog ≤ 1 s and its refresh ≤ 0.5 s at p95 with 600 items; the form ≤ 0.5 s.

**Scale/Scope**: the demo (tens to 200 use cases).

## Constitution Check

| Article | How this plan complies |
| --- | --- |
| I, II Spec-driven, no values | form layout and allowed values are seed data; no field or type names in simulator code |
| III Agents build, humans decide | the form only saves a person's fields; the platform decides and answers (016) |
| IV Separation of duties | every save and comment is attributed to the signed-in user |
| V Evidence-first | the evidence link puts the console's run page in front of the person before a decision |
| VII Interfaces | the REST contract is unchanged; the platform reads the seed only as data in a test |
| IX Test first | sanitiser, layout, inputs, diffing, history and tree are test first |
| XI Secure | allow-list sanitiser, escaping, CSRF, `rel="noopener noreferrer"`, revision checks |
| XII Simplicity | no new dependency, no new table |

**Result: pass.**

## Project Structure

```text
ado_sim/src/ado_sim/
├── pages/sanitize.py         allow-list HTML for display
├── pages/form.py             layout, inputs by type, changed fields → patch, history entries
├── pages/backlog.py          the tree
├── pages/routes.py           form GET/POST, comments, backlog and its fragment
├── pages/templates/          item.html → form.html, backlog.html, rows.html, nav in base.html
├── seed.py, process.py       form layout (validation, storage, read)
ado_sim/seed/demo.yaml        form layout; decision allowed values
ado_sim/tests/unit/           test_sanitize.py, test_form.py, test_form_layout.py, test_backlog.py
ado_sim/tests/pages/          test_form_page.py, test_backlog_page.py (test_item.py retired)
ado_sim/tests/properties/     test_backlog_timing.py, test_concurrent_saves.py, test_hostile_values.py
tests/contract/board/         test_decision_values.py (platform; reads both data files)
```

## Complexity Tracking

None.
