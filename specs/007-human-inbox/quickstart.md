# Quickstart: Human Inbox

## 1. Tests (no browser, no network)

```bash
uv run pytest tests/unit/api tests/integration/api -q   # API operations over the test database
uv run pytest tests/integration/ui -q                    # Streamlit pages through the real API
make check
```

**Expect**:

- every operation refuses requests without a session;
- inbox items appear only for people who may act;
- decisions, edits, uploads, attachments, clarifications, escalations and waivers work through
  the API;
- stale decisions are refused;
- attachments come back with the download-only headers.

## 2. Live stack

```bash
make up
open http://localhost:${ADLC_UI_PORT:-8501}
```

1. Sign in as a business owner from your account file and submit a use case.
2. Sign in as the T0 approvers and decide from the inbox.
3. Continue to T1: edit a KPI cell. Check that the detail shows a person version and the
   re-checked controls.
4. Then pass with a reason if the reviewer recommended otherwise.
5. Open the use case journey and verify the ledger.

**Expect**:

- the journey and the inbox update within 30 s;
- `adlc-ledger verify --usecase <id>` reports verified;
- API spans in Jaeger carry `account`.
