# Quickstart: validating Lifecycle Orchestration (003)

The orchestration contracts are in [contracts/](contracts/). The scenarios run against the
real registered `adlc-specs/`, with stub agents.

## 1. Transition table and properties (US1–US4, constitution III)

```bash
uv run pytest tests/unit/orchestration -q
```

**Expect**: every row of contracts/state-machine.md is accepted, everything else is rejected,
and the four hypothesis properties hold.

## 2. Demo scenarios with stubs (SC-001, SC-002)

```bash
uv run pytest tests/scenario -q
```

**Expect**:

- **Happy path**: T0→T9 with one closed run per terminal.
- **D-2**: a T1 rework carries the comment into run 2.
- **D-3**: T4 `implementation` opens T3.
- **D-4**: the fourth T1 rework opens escalated.
- **D-7**: `T8.event.drift` → T9 → `T9.reentry.T2` → T2.
- **D-9**: a T2 clarification is answered, the same run resumes, and the rework count is 0.
- **D-5**: a T5 exception is approved by `risk_owner` and routes to T6.

Run the scenario suite 10 times and expect 10 passes:

```bash
for i in $(seq 10); do uv run pytest tests/scenario -q -p no:randomly || break; done
```

## 3. Reliability (US6, SC-004 to SC-007)

```bash
uv run pytest tests/integration/orchestration -q
```

**Expect**:

- A restart in each waiting state continues correctly.
- Double delivery gives no duplicate runs.
- A failing delivery is dead-lettered after exactly 5 attempts and delivered once after
  re-queue.
- Every closed run has its ledger record and event, written together.

## 4. Live stack

```bash
make up                                   # migrate → register → api → orchestrator
make status                               # orchestrator healthy (heartbeat < 30 s)
uv run python -m scripts.demo_drive happy-path   # drives submit + decisions through the service
```

**Expect**: the T0→T9 path completes. Inspect the routing latency:

```bash
docker compose -f deploy/compose.yaml --env-file .env exec postgres psql -U adlc_owner -d adlc -c \
  "SELECT run_id, state, final_status, closed_at FROM run.terminal_run ORDER BY opened_at;"
```

The p95 gap between a run's `closed_at` and the next run's `opened_at` is ≤ 2 s (SC-003).
