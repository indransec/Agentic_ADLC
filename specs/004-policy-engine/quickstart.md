# Quickstart: validating the Policy Engine (004)

## 1. Predicates, parameters, authorization (pure)

```bash
uv run pytest tests/unit/policy -q
```

**Expect**:

- Each of the 60 predicates has a passing case, and a failing case with its reason asserted.
- Parameter resolution is correct for stricter, equal, looser and absent values at every tier.
- The deny-wins and default-deny properties hold.
- Unknown predicates and evaluation errors fail closed.

## 2. Every rule in T0–T9 (SC-001, SC-002, SC-008)

```bash
uv run pytest tests/integration/policy/test_all_rules.py -q -s
```

**Expect**:

- All 98 prerequisite and control expressions evaluate with no engine error.
- With the synthetic data, every blocking one passes.
- The p95 time per control is printed and is under 50 ms.

## 3. Decision log (SC-004, SC-009)

```bash
uv run pytest tests/integration/policy/test_decision_log.py -q
```

**Expect**:

- One row per call; UPDATE and DELETE are refused.
- Decisions that read synthetic evidence are labelled, and no others are.

## 4. Lifecycle with the real engine (SC-007)

```bash
uv run pytest tests/scenario -q
```

**Expect**: happy path, D-2, D-3, D-4, D-5, D-7 and D-9 pass with real checks.

## 5. Live stack

```bash
make up && uv run python -m scripts.demo_drive
docker compose -f deploy/compose.yaml --env-file .env exec postgres psql -U adlc_owner -d adlc -c \
  "SELECT check_id, passed, synthetic, reason FROM run.policy_decision ORDER BY policy_decision_id LIMIT 20;"
```

**Expect**:

- The happy path completes.
- Decisions are listed with reasons.
- Rows for T3 onward show `synthetic = true` where CI, red-team or similar evidence was read.
