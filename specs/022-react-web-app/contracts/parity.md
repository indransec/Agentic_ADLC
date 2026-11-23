# Contract: Parity checklist (condition for removing Streamlit, FR-026)

Every row must be `passing` before the cutover commit (research R-14).

- **Component** means Vitest (`web/src/**`).
- **E2E** means Playwright (`web/e2e/*.spec.ts`).
- **API** means pytest.

## Rows from today's AppTest suite

| # | Today (`tests/integration/ui/…`) | Rebuilt by | Status |
| --- | --- | --- | --- |
| P-01 | `test_intake.py::test_sign_in_submit_and_follow` | E2E `intake.spec.ts`; Component `pages/intake/intake-page.test.tsx` | passing |
| P-02 | `test_intake.py::test_sign_out_and_expired_session` | E2E `session.spec.ts` (sign-out, expired cookie → sign-in with `next`) | passing |
| P-03 | `test_intake.py::test_refused_submission_shows_the_reason` | Component `intake-page.test.tsx` (422 `field` beside the field) | passing |
| P-04 | `test_sign_off.py::test_inbox_detail_and_pass` | E2E `sign-off.spec.ts`; Component `pages/inbox/inbox-page.test.tsx` | passing |
| P-05 | `test_sign_off.py::test_reason_field_follows_the_recommendation` | Component `pages/run/decision-form.test.tsx` | passing |
| P-06 | `test_sign_off.py::test_stale_answer_reloads_with_a_message` | E2E `stale.spec.ts`; Component `decision-form.test.tsx` | passing |
| P-07 | `test_sign_off.py::test_plain_text_for_agent_text` | Component `pages/run/run-page.test.tsx` (rendering samples) | passing |
| P-08 | `test_sign_off.py::test_inbox_groups_by_kind_and_marks_controls_being_rerun` | Component `inbox-page.test.tsx` | passing |
| P-09 | `test_artifacts.py::test_editor_saves_a_change` | E2E `artifacts.spec.ts`; Component `pages/run/artifact-panel.test.tsx` | passing |
| P-10 | `test_artifacts.py::test_read_only_for_non_editors` | Component `artifact-panel.test.tsx` | passing |
| P-11 | `test_artifacts.py::test_large_tables_are_read_only_with_upload_offered` | E2E `artifacts.spec.ts` (1,000 editable, 1,001 read-only); Component `artifact-panel.test.tsx` | passing |
| P-12 | `test_artifacts.py::test_attach_and_download_only` | E2E `artifacts.spec.ts` (download event, no inline render) | passing |
| P-13 | `test_rendering.py::test_text_from_agents_and_people_is_plain` | Component `ui/literal.test.tsx` and every page test's markup and script samples; E2E `rendering.spec.ts` (no script runs, no CSP violation) | open |
| P-14 | `test_blocked.py::test_blocked_run_shows_why_and_can_be_terminated` | Component `run-page.test.tsx` | passing |
| P-15 | `test_requests.py::test_answer_a_clarification` | Component `pages/requests/clarification-page.test.tsx`; E2E `requests.spec.ts` | passing |
| P-16 | `test_requests.py::test_complete_an_escalation` | Component `escalation-page.test.tsx`; E2E `requests.spec.ts` | passing |
| P-17 | `test_requests.py::test_decide_a_waiver` | Component `waiver-page.test.tsx`; E2E `requests.spec.ts` | passing |
| P-18 | `test_requests.py::test_dead_letters_for_the_coe` | Component `pages/dead-letters/dead-letters-page.test.tsx` (CoE and non-CoE) | open |
| P-19 | `test_evidence.py::test_evidence_and_verify` | Component `pages/use-cases/use-cases-page.test.tsx`; `run-page.test.tsx` (evidence tab) | open |
| P-20 | `test_changes.py::test_approver_decides_a_change_in_the_inbox` | Component `inbox-page.test.tsx` | passing |
| P-21 | `test_changes.py::test_others_see_no_change_requests` | Component `inbox-page.test.tsx` | passing |
| P-22 | `test_dashboard.py::test_journey_page_draws_lanes_strip_and_panel` | Component `pages/journey/journey-page.test.tsx` (figure built from the answer) | open |
| P-23 | `test_dashboard.py::test_refresh_follows_the_setting` | Component `journey-page.test.tsx` (fake timers, `/config.json`); API `tests/integration/web/test_server.py` | open |
| P-24 | `test_dashboard.py::test_activity_filters_survive_a_refresh` | Component `pages/activity/activity-page.test.tsx` | open |
| P-25 | `test_dashboard.py::test_portfolio_page` | Component `pages/portfolio/portfolio-page.test.tsx` | open |
| P-26 | `test_dashboard.py::test_dead_letter_payload_for_the_coe` | Component `dead-letters-page.test.tsx` | open |
| P-27 | `tests/unit/test_ui_boundary.py` | ESLint rules (R-11) plus a boundary test retargeted to `adlc.web` | passing |

## Rows new to the rebuild

| # | Behaviour | Test | Status |
| --- | --- | --- | --- |
| N-01 | Session not readable by scripts or storage (SC-003) | E2E `session.spec.ts` | passing |
| N-02 | Cross-site change refused (SC-004) | API `test_csrf.py`; E2E `session.spec.ts` | passing |
| N-03 | Deep link opens a run after sign-in | E2E `session.spec.ts` | passing |
| N-04 | Back, forward and reload keep page, run and filters | E2E `navigation.spec.ts` | open |
| N-05 | Refresh does not discard typed input | Component `inbox-page.test.tsx`, `journey-page.test.tsx` | passing |
| N-06 | Platform unreachable: message and input kept | Component `api/client.test.ts`; API `test_server.py` (502) | passing |
| N-07 | Keyboard-only and axe scan on every page | E2E `a11y.spec.ts` | open |
| N-08 | Answer shapes unchanged by models (SC-006) | API `test_response_shapes.py` | passing |
| N-09 | Contract drift fails the check (SC-008) | `test_openapi_fresh.py`; `web-typecheck` | passing |
| N-10 | Page timing on demo data (SC-007) | E2E `timing.spec.ts` | open |
