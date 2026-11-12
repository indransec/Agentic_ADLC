---
id: PB-T4-02
version: "1.1.0"
title: Golden dataset
owner_role: qa_eval_lead
status: active
---
# Golden dataset

- Evaluate only on datasets in the dataset registry: each has an id, a version, a seed, a size and
  a content hash, so the same dataset is the same cases every time.
- The golden dataset covers every category, priority and edge case the requirements name; the
  regression dataset is larger and becomes the regression pack later terminals re-run.
- Datasets in the MVP are synthetic; record them as 100% synthetic. Planted personal data appears
  only in datasets made for privacy tests.
- Never send a dataset's labels (expected answers) to the agent under test; the harness keeps them
  for scoring.
