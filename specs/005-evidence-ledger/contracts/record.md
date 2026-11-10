# Contract: Ledger record content

## Version 2 (written from this feature on)

```json
{
  "content_version": 2,
  "run_id": "UC-0001/T1/run-2",
  "usecase_id": "UC-0001",
  "terminal_id": "T1",
  "spec": {"version": "1.0.0", "content_hash": "sha256:…"},
  "trigger": {"event_type": "T1.rework.requirement", "event_id": "…", "context": {}},
  "final_status": "pass",
  "decisions": [{"role": "product_owner", "person": "…", "decision": "pass", "signed_at": "…"}],
  "reviewer_recommendation": {"status": "pass", "checklist_scores": {}, "findings": []},
  "control_results": [{"id": "CTL-T1-01", "passed": true, "blocking": true, "reason": "passed", "synthetic": false}],
  "clarification_rounds": [],
  "waiver": null,
  "emitted": {"kpis": {"artifact": "kpis", "version": 2, "content_hash": "sha256:…"}},
  "profile_version": 1,
  "artifacts": [
    {"id": "kpis", "version": 2, "content_hash": "sha256:…", "schema_valid": true,
     "producer": {"type": "person", "id": "owner.product"},
     "attachments": [{"content_hash": "sha256:…", "name": "kpis.xlsx",
                      "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      "size": 9812}]}
  ],
  "bound_to": null
}
```

## Rules

- **Hashes**: `content_hash` is `sha256:` plus the SHA-256 of `normalise(content)`. The
  `previous_record_hash` column holds the previous record of the use case (as in 003).
- **Ledger key**: as in 003.
- **Artifacts**: listed in spec order, with the latest version of each. An artifact the run never
  produced is absent.
- **`bound_to`**: the spec's `evidence.ledger.bound_to` resolved through the latest closed run of
  the referenced terminal, or `null` when the spec has no binding.

## Version 1 (feature 003 baseline)

Version-1 records have no `content_version`. Their `artifacts` hold inline rows, and they have
no `profile_version` and no `bound_to`. They are verified for hash and chain only.
