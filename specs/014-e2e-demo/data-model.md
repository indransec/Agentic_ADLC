# Data Model: End-to-End Demo (feature 014)

No new tables.

- **Demo script** (`demo/script.yaml`): `reference` (use case id), `steps[]`: `number`,
  `terminal`, `proves` (D-n list), `actions[]` (`decide {role, decision, comment?, root_cause?,
  reason?, fields?}`, `answer {role, text}`, `approve_change {}`, `approve_waiver {}`,
  `complete_escalation {role}`, `fault {name, action}`), `expect {state?, final_status?, arrow?}`.
- **Demo report**: steps (number, terminal, outcome, run ids, seconds), moments (D-n → evidence).
- **Trace report**: per record kind (sign-off, control decision, event, artifact version) the
  spec version, actor, hash; gaps; chain verification.
