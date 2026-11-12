---
id: PB-T5-01
version: "1.1.0"
title: T5 assurance
owner_role: adlc_coe
status: active
---
# T5 assurance

## Purpose

Show, with evidence from runs and the control library, that the candidate package is secure,
private and responsible enough to release at its risk tier, and state every remaining risk with an
owner. Gaps are never hidden: a control that cannot be met fails, and people decide on rework or
an exception with a waiver.

## Procedure

1. `pilot_env_create` (the test environment runs the candidate) and `pilot_env_status`.
2. `redteam_harness_run` (all categories) and `dlp_scanner_run` on the personal-data dataset.
3. `control_library_read` by topic (`security`, `privacy`, `rai`) and `iam_read`.
4. `grc_write` the assurance report: what was tested, the rates and findings, the gaps and the
   residual risks.

## Steps per artifact

1. **threat_model_results** (`threat_id, threat, test, result, residual_risk`): T2's threats plus
   one row per red-team category; `test` names the suite and category; `result` `mitigated` only
   when the category's success rate is within the tier maximum.
2. **security_control_evidence** (`control_id, implemented, evidence_link`): control-library ids;
   `evidence_link` names the result (`RES-<n>`) or report (`GRC-<n>`).
3. **access_control_matrix** (`identity, resource, permission, justification`): the agent's
   identities and the tools and data it may use, each permission justified by a T2 design row.
4. **privacy_assessment**, **regulatory_map**: per the privacy-impact-assessment and
   regulatory-mapping playbooks (PB-T5-03, PB-T5-04).
5. **rai_assurance** (`rai_metric, t4_actual, threshold, accepted`): one row per T1 RAI threshold,
   `t4_actual` copied from the harness result for that metric name ("not measured" if absent).
6. **resilience_verification** (`scenario, expected_fallback, observed, result`): safe-fail,
   fallback to a person, degradation and the kill switch. The kill switch exists only in prod-sim
   and is not yours to invoke: record it with `observed` "not run in test" and `result` `fail`, so
   the approvers decide (rework, or an exception whose compensating control is the kill-switch
   check at release).
7. **residual_risk_register** (`risk_id, risk, rating, risk_owner, decision, review_date`): every
   gap and residual risk with a named owner role and a proposed decision.
8. **assurance_attestation**: never write it; the approvers' sign-off is the attestation.
