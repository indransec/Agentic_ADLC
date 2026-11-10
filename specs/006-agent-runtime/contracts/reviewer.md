# Contract: Reviewer Output

The reviewer answers with one JSON object of one of two shapes.

```json
{
  "scores": {"CHK-T1-01": 3, "CHK-T1-02": 2, "CHK-T1-03": 3, "CHK-T1-04": 1, "CHK-T1-05": 2},
  "findings": [
    {"item": "CHK-T1-04", "text": "KPI-02 target is not supported by the baseline"},
    {"item": null, "text": "Overall consistent with the T0 problem"}
  ],
  "recommendation": {"status": "rework", "reason": "Thresholds unrealistic", "root_cause": "requirement"}
}
```

```json
{
  "clarification": {
    "questions": ["Which channels are in scope for the first release?"],
    "addressed_role": "product_owner",
    "looked_in": ["intake", "T1.user_experience", "PB-T1-01"]
  }
}
```

## Validation (output that breaks any rule does not fit)

- `scores` holds exactly the checklist item ids of the run's terminal, each an integer from 0 to
  3.
- `findings[].item` is null or a checklist item id. `text` has 1 to 1,000 characters.
- `recommendation.status` is one of `pass`, `rework` or `exception`. `reason` has 1 to 1,000
  characters.
- `root_cause` is required when the status is `rework`, and must be an id in
  `root_causes.yaml`.
- `clarification.questions` has 1 to 5 items, and `looked_in` at least one. `addressed_role`,
  when given, is a role in `roles.yaml`.
- No other keys are allowed.

## Builder output (the agents' artifacts)

```json
{"artifacts": {"<artifact_id>": [{"<column>": "<value>", "...": "..."}]}}
```

The alternative is `{"clarification": {...}}`, the same shape as above.

- **Which artifacts:** every artifact with `applicability.mode: mandatory` must be present. An
  artifact with mode `conditional` is required when its `when` condition holds for the run (the
  policy engine evaluates it), and is optional otherwise. No undeclared artifact is allowed.
- **Shape:** every artifact, whatever its `format` (`table`, `reference`, `signed_record`,
  `document`, `diagram+table`), is a list of rows whose keys are exactly the declared columns.
  This matches how feature 005 stores and checks versions.
