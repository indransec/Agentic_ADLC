# tests/scenario

Demo-moment scenarios, driven through `OrchestratorService` against the real registered
`adlc-specs/`. Since feature 004 they run with the real policy engine. The stub agent starts
from the synthetic artifacts in `data/synthetic/`, and synthetic evidence is labelled in every
decision. Each test gets its
own database, copied from a migrated and registered template (`tests/support/orchestration.py`).

| Demo moment | Tests |
| --- | --- |
| D-1 agent builds, reviewer recommends, human decides, at every terminal | `test_d1_agent_reviewer_human.py` (after an escalation a person completes the run instead of the reviewer recommending: the 003 design), `test_happy_path.py` |
| D-2 rejection with comment, rework uses it | `test_d2_rework_with_comment.py` |
| D-3 root-cause routing across terminals | `test_d3_rework_root_cause.py` |
| D-4 escalation after 3 rework cycles | `test_d4_rework_limit_escalation.py` |
| D-5 exception with waiver, rechecked at T6 | `test_d5_exception_waiver.py` |
| D-6 what T4 tested is what T7 deployed | `test_d6_hash_integrity.py`, `test_reference_replay_t6_t9.py` |
| D-7 T8 event → T9 → re-entry or retirement | `test_d7_drift_reentry.py`, `test_reference_replay_t6_t9.py` |
| D-8 live dashboard | `test_d8_dashboard.py` |
| D-9 clarification, same run, not rework | `test_d9_clarification.py` |
| Negatives (no agent sets an outcome or deploys an unauthorised hash) | `test_negative_agents.py`, `tests/integration/agents/test_acting_scopes.py` |

D-1, D-6 and D-8 run the demo script itself (`demo/script.yaml`, `demo_run.py`) in `--auto` over
the fake pilot, with the rehearsed replies the live demo uses.

Earlier scenario files:

| Test | Demo moment |
| --- | --- |
| `test_happy_path.py` | T0→T8 pass with one ledger chain; T9 opens on operational events |
| `test_d2_rework_with_comment.py` | D-2: rework comment reaches the next build |
| `test_d3_rework_root_cause.py` | D-3: T4 `implementation` → T3 |
| `test_d4_rework_limit_escalation.py` | D-4: the fourth rework opens escalated |
| `test_d5_exception_waiver.py` | D-5: exception approved by `risk_owner` |
| `test_d7_drift_reentry.py` | D-7: drift → T9 → `T9.reentry.T2` → T2 |
| `test_d9_clarification.py` | D-9: clarification answered; same run; not rework |

Feature 014 adds the demo script and its driver (`demo/`, `adlc-demo`).
