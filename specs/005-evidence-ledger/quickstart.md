# Quickstart: validating the Evidence Ledger (005)

## 1. Pure rules

```bash
uv run pytest tests/unit/ledger -q
```

**Expect**:

- Record content version 2 hashes the same regardless of key order.
- Profile merge replaces values by name.
- Spreadsheet rows are parsed as described in contracts/artifacts.md.
- The verification rules flag each tamper case.

## 2. Ledger in the lifecycle (SC-001, SC-002, SC-004, SC-005, SC-006)

```bash
uv run pytest tests/integration/ledger -q
```

**Expect**:

- Every artifact hash in every record resolves to identical stored content.
- Human edits create `person` versions, and an Excel upload becomes rows plus an attachment.
- The profile grows with T0–T2, and `param.*` uses profile values.
- Identical content is stored once.

## 3. Tamper detection (SC-003)

```bash
uv run pytest tests/integration/ledger/test_tamper.py -q
```

**Expect**: an altered record, an altered artifact, a missing attachment, a broken chain and a
binding mismatch are each reported with their location.

## 4. Regression (SC-008)

```bash
uv run pytest tests/scenario -q
```

## 5. Live stack

```bash
make up && uv run python -m scripts.demo_drive
docker compose -f deploy/compose.yaml --env-file .env exec orchestrator adlc-ledger verify --usecase UC-0001
```

**Expect**: `verified` for the use case, with the number of records checked, and the
verification run recorded.
