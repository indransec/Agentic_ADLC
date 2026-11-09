# Contract: Validation rules

Every rule has a stable id, level, default severity and at least one negative fixture in
`tests/fixtures/specs/<rule-id>/`. A unit test asserts that this table and the rule table in
code list the same ids. Ids V-01 to V-10 keep their TDS Annex B.5 meaning.

| Id | Level | Severity | Check | Example finding |
| --- | --- | --- | --- | --- |
| P-01 | L1 | error | File parses as YAML (or as front matter for playbooks) | `T2.yaml:14:3 mapping values are not allowed here` |
| P-02 | L1 | error | Expected layout: each catalogue file present once; terminal files named `T<n>.yaml`; checklist files `t<n>.yaml` | `shared/predicates.yaml missing` |
| P-03 | L1 | info | Later checks (L3–L5) skipped for a file that has L1 or L2 errors, so the skip is visible rather than silent | `terminals/T2.yaml: L3–L5 checks skipped (earlier errors)` |
| S-01 | L2 | error | Terminal spec matches `terminal.schema.json` (unknown fields refused) | `/terminal/controls/automated/0/rul: unknown field` |
| S-02 | L2 | error | Catalogue matches its schema | `shared/metrics.yaml /metrics/3/unit: required` |
| S-03 | L2 | error | Checklist and playbook front matter match their schemas | `playbooks/t0-intake.md: version missing` |
| V-01 | L3/L4 | error | Ids unique within a spec (L3); terminal id unique across the folder (L4) | `CTL-T3-02 defined twice` |
| V-02 | L4 | error | Every `T<n>.<artifact>[.<field>]` reference names an artifact column or emitted value of terminal `T<n>`, and `T<n>` can reach the referencing terminal in the route graph | `T2 references T5.attestation but T5 cannot reach T2` |
| V-03 | L4 | error | Every `trigger.on` event is produced by some terminal or is external in `events.yaml` | `T5 triggers on T8.event.safety_breech: no producer` |
| V-04 | L3 | error | Every non-terminating outcome (pass, rework, exception, escalate) has `route`, `route_by_root_cause` or `not_allowed: true` | `T6 exception has no route` |
| V-05 | L3/L4 | error | Roles exist in `roles.yaml` (L4); every `sign_off` role holds A or R in `human_roles` (L3) | `T4 sign_off role product_owner holds only C` |
| V-06 | L4 | error | Every tool scope and grounding server exists in `mcp_servers.yaml` | `mcp:gitt:branch_write unknown` |
| V-07 | L3 | error | No permission in both `allow` and `deny` | `write:repo in allow and deny` |
| V-08 | L3 | error | Every tiered value defines `low`, `medium`, `high` | `timeline.expected_duration missing high` |
| V-09 | L3 | error | `status_rights.agent` never contains pass, exception or terminate | |
| V-10 | L4 | error | Every playbook ref and checklist ref exists at the stated version, and every checklist item id in the spec exists in the checklist file | `PB-T3-02 1.0.0 not found` |
| V-11 | L3 | error | Every condition, rule, `when` and threshold expression parses as CEL | `CTL-T1-02 rule: unexpected token '>'` |
| V-12 | L4 | error | Every identifier in an expression resolves (research R-02): predicate, `param.*` guardrail, `tier.*` key of this spec, `run.*` variable, evidence source, terminal artifact; every root cause, change class, data class, model tier, risk tier, route destination and event is from its catalogue | `param.injection_success_max unknown` |
| V-13 | L4 | error | Predicate calls match the signature in `predicates.yaml` (arity and argument kinds) | `all_rows_have expects 2 arguments, got 1` |
| V-14 | L3 | error | Every artifact has `applicability`; `conditional` has `when`; `mandatory` has no `when` | `T9 retirement_record conditional without when` |
| V-15 | L3 | error | Status rights follow constitution III: `human` may hold pass, rework, exception, terminate; `reviewer` only recommend; `orchestrator` only escalate and `rework_on_auto_rollback`; `agent` only `raise_event`; `set_by` lists roles only | `reviewer has pass` |
| V-16 | L4 | error | One terminal's `allow` permissions do not match more than one duty group in `permissions.yaml` | `T3 allow spans build and deploy` |
| V-17 | L4 | error | Every pass, exception and root-cause route to another terminal targets a terminal that subscribes to the matching event (`T<n>.pass`, `T<n>.exception`, `T<n>.rework.<cause>`); routes to itself need no subscription | `T4 rework.design → T2 but T2 does not subscribe to T4.rework.design` |
| V-18 | L3/L4 | error | Annex A naming: ids (`PRE-`, `CTL-`, `CHK-`, `PB-`, `MON-`), agent ids, permissions, scopes, metrics (`_rate`, unit suffixes), guardrails (`_min`/`_max`), columns (unit suffixes for numeric columns flagged in the metric catalogue) | `guardrail max_injection_success: expected <measure>_<min\|max>` |
| V-19 | L4 | error | Tighten-only guardrails are monotonic across tiers (research R-08) | `injection_success_max high 0.05 > low 0.02` |
| V-20 | L3 | error | File name matches `metadata.id` | `T3.yaml has metadata.id T4` |
| V-21 | L3 | error | `human_roles` has exactly one A per scope | `two A roles for whole terminal` |
| V-22 | L4 | error | Every terminal is reachable from an external event and can reach a terminating destination (`terminate`, `lifecycle_closed`) in the route graph | `T6 cannot reach a terminating outcome` |
| V-23 | L4 | info | Predicate or MCP server not used by any spec (metrics are used by use-case profiles, not specs) | `predicate is_frozen unused` |
| V-24 | L5 | error | Content changed versus baseline requires a version bump of at least the level in research R-10; a missing baseline ref gives a `warning` | `T0 changed (route) needs major bump; 1.0.0 → 1.0.1` |
| V-25 | L5 | error | Version never decreases versus baseline | `T3 1.2.0 → 1.1.0` |
| V-26 | L4 | warning | Guardrail or tiering value marked `proposed_default` (reported so owners can confirm; does not fail) | `param.judge_agreement_min is a proposed default` |

Registration-time refusals (database or register code, not validation findings):

- **R-01**: changed content under an already registered version.
- **R-02**: retiring a version that is pinned.
- **R-03**: a second active version.
