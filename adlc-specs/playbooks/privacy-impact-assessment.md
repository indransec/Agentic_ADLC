---
id: PB-T5-03
version: "1.1.0"
title: Privacy impact assessment
owner_role: privacy_officer
status: active
---
# Privacy impact assessment

- **privacy_assessment** (`data_element, data_class, masking, retention, lawful_basis`): one row per
  data element in T2's data strategy; `data_class` from the data class catalogue and never above
  the approved maximum; `masking` states how personal data is masked in logs and answers;
  retention and lawful basis as T2 and the data owner stated.
- Run the personal-data scan on the dataset with planted data: findings (masked) mean answers
  expose personal data. Any finding is a gap that fails the leak control.
- Logs and traces must keep identifiers only; if you cannot show that, record it as a gap.
