# Dictionary changes: TDS Annex B 1.0.0 → 1.1.0

`terminal.schema.json` implements the TDS Annex B dictionary (schema version 1.0.0) with the
changes below. Each one should be carried back into TDS Annex B. Terminal specs declare
`metadata.schema_version: "1.1.0"`.

## Additions

| Field | Type | Reason |
| --- | --- | --- |
| `evidence.artifacts[].applicability` | `{mode: mandatory \| conditional \| optional, when?: expr, reason?: string}` | Superset and applicability (SA §5.2). Replaces `required`; `required: on_retire` becomes `{mode: conditional, when: run.mode == "retire"}`. |
| `evidence.artifacts[].description` | string | Optional prose |
| `prerequisites[].description`, `controls.automated[].description`, `monitors[].description` | string | Keeps the TDS wording of each converted condition (spec FR-013) |
| `outcome_model.<status>.description` | string | Replaces free-text annotations such as T6 `example` and T9 `meaning` |
| `outcome_model.<status>.alternatives` | list of destinations | T9 `or: lifecycle.closed` |
| `outcome_model.<status>.notify` | list of roles | Escalation to boards plus named roles (T5–T9) |
| `outcome_model.rework.on` | snake_case | T7 rework `on: auto_rollback` |
| `outcome_model.event_routes.<event>.then_when` | expr | Conditional follow-on route (T8 `if_sev1`) |
| `authorities.sign_off.plus` | `[{role, when: expr}]` | T3 conditional approver (was free text) |
| `authorities.sign_off.external` | `{body, when?: expr}` | T6 CAB (was free text) |
| `authorities.sign_off.by_tier`, `.by_mode` | maps of sign-off rules | Replace `sign_off.<tier>` and `sign_off.<mode>` so the schema can tell the forms apart |
| `change_classes.<class>.alternative` | destination | T9 strategic `or: retire` |
| `controls.checklist.version` | semver | V-10 checks the checklist file at this version |
| `timeline.clarification_sla` | duration (required) | SA §6.2 clarification timer |
| `timeline.max_clarification_rounds` | int ≥ 0 (required) | SA §6.2; proposed default 2 |
| `timeline.max_auto_retries` | int ≥ 0 (optional) | TDS Annex A.3 note: limit on automated-control retries; proposed default 3 |
| `timeline.retirement_duration` | tiered duration | T9 retirement SLA, separate from the assessment SLA |

## Changed meaning or form

| Field | Change | Reason |
| --- | --- | --- |
| Expressions (`condition`, `rule`, `when`, `threshold`, `applies_when`) | CEL syntax: `&&`, `\|\|`, `!`, `in ["a"]`; existence words become predicates (`evidence_exists`, `is_signed`, `is_frozen`, `is_provisioned`, `is_pinned`, `is_live`) | SA §5.5 "expressions in CEL or named predicates" |
| Names in expressions | Namespaced roots: `T<n>.*` (evidence), `param.*` (guardrails), `tier.*` (`controls.tiering` keys), `timeline.*` (own timeline), `run.*` (run variables `rework_count`, `age`, `now`, `usecase_id`, `run_version`, `risk_tier`, `mode`), evidence sources from `shared/evidence_sources.yaml` | Avoids collisions between run variables and artifact columns; makes every name checkable (V-12) |
| `tier.<param>` for safety limits | Becomes `param.<name>` from `shared/guardrails.yaml` | Constitution II; spec FR-014 |
| `controls.checklist.items` | List of ids only; text lives in `checklists/t<n>.yaml` | Data and prose kept apart; V-10 checks the ids |
| `outcome_model.<status>.set_by` | Always a list of roles | One shape for all terminals |
| `outcome_model.<status>.route` | Terminal id, event, destination from `shared/route_destinations.yaml`, or `${...}` template | Escalations to boards and resolvers (`owning_terminal`) need named destinations |
| `timeline.reminder_after`, `escalate_after` for `mode: continuous` | Measured from `review_due` | TDS T8 `2d_past_review_due` |
| `timeline.expected_duration` | Tiered duration or `continuous` only | T7 `1d+3d_hypercare` split: hypercare length lives in `controls.tiering.hypercare` |
| Durations | `<int>(h\|d\|w\|m)` as in TDS B.1 (`m` = months) | Unchanged; enforced by the schema |
| Artifact columns | Numeric columns carry Annex A unit suffixes (`_count`, `_pct`, `_usd`, `_rate`) | SA Annex A closing note |

## Removed

| Field | Reason |
| --- | --- |
| `evidence.artifacts[].required` | Replaced by `applicability` |
| `authorities.sign_off.applies_to` (T8) | Implied: sign-off on a continuous terminal is the periodic review |
| `outcome_model.<status>.example`, `meaning`, `or` | Replaced by `description` and `alternatives` |
