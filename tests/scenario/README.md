# tests/scenario

Demo-moment scenarios, driven through `OrchestratorService` against the real registered
`adlc-specs/`. Since feature 004 they run with the real policy engine. The stub agent starts
from the synthetic artifacts in `data/synthetic/`, and synthetic evidence is labelled in every
decision. Each test gets its
own database, copied from a migrated and registered template (`tests/support/orchestration.py`).

| Test | Demo moment |
| --- | --- |
| `test_happy_path.py` | T0→T8 pass with one ledger chain; T9 opens on operational events |
| `test_d2_rework_with_comment.py` | D-2: rework comment reaches the next build |
| `test_d3_rework_root_cause.py` | D-3: T4 `implementation` → T3 |
| `test_d4_rework_limit_escalation.py` | D-4: the fourth rework opens escalated |
| `test_d5_exception_waiver.py` | D-5: exception approved by `risk_owner` |
| `test_d7_drift_reentry.py` | D-7: drift → T9 → `T9.reentry.T2` → T2 |
| `test_d9_clarification.py` | D-9: clarification answered; same run; not rework |

Feature 014 adds the end-to-end demo through the UI.
