# Quickstart: validating Platform Foundation (001)

A run guide that proves each user story works end to end. Commands and formats are defined in
[contracts/make-targets.md](contracts/make-targets.md),
[contracts/settings.md](contracts/settings.md) and [contracts/files.md](contracts/files.md).

## Prerequisites

- Docker with Compose v2, running
- uv, GNU make, git
- Free host ports 8000, 5432 and 16686 (or override them in `.env`)

## 1. Configure (US3)

```bash
make install
cp .env.example .env                                  # fill every REPLACE_ME value
mkdir -p ~/.config/adlc
cp deploy/accounts.example.yaml ~/.config/adlc/accounts.dev.yaml
uv run adlc-account hash                              # paste output into credential_hash
set -a; source .env; set +a
uv run adlc-account check                             # expect: OK, n accounts (dev)
```

**Expect**: `adlc-account check` exits 0. With `ADLC_ENV=demo` and a placeholder left in, it
exits 1 and names the account.

## 2. Start, check health, restart (US1)

```bash
make up            # returns when all services are healthy
make status        # postgres, jaeger, api: healthy; migrate: exited (0)
curl -s localhost:8000/health
```

**Expect**: `{"status":"ok","checks":{"database":"ok"}}` in under 3 minutes from `make up`.
Run `make down && make up`, then confirm that data written in step 4 is still there.

## 3. Missing setting (US3)

```bash
set -a; source .env; set +a
ADLC_SESSION_SECRET= uv run adlc-api      # empty counts as missing
```

**Expect**: exit code 2 and the line `ADLC_SESSION_SECRET: missing; …`, with no secret
values printed.

## 4. Ledger immutability (US2)

Insert one row as `adlc_app`, then try to change it as both identities:

```bash
docker compose -f deploy/compose.yaml --env-file .env exec postgres psql -U adlc_app -d adlc -c \
  "INSERT INTO ledger.ledger_record (ledger_key, content_hash) VALUES ('qs/1', 'sha256:$(printf '0%.0s' {1..64})');"
docker compose -f deploy/compose.yaml --env-file .env exec postgres psql -U adlc_app   -d adlc -c "UPDATE ledger.ledger_record SET ledger_key='x';"
docker compose -f deploy/compose.yaml --env-file .env exec postgres psql -U adlc_owner -d adlc -c "DELETE FROM ledger.ledger_record;"
```

**Expect**: the insert succeeds. The UPDATE as `adlc_app` and the DELETE as `adlc_owner` both
fail with `ledger.ledger_record is append-only`, and the row is unchanged.

## 5. Migration round trip (US2)

```bash
make migration-check
```

**Expect**: upgrade → downgrade → upgrade succeeds on a fresh database, and the four schemas
and both triggers exist at the end.

## 6. Sign-in (US4)

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/sign-in -H 'content-type: application/json' \
  -d '{"account_name":"owner.business","password":"<yours>"}' | jq -r .token)
curl -s localhost:8000/auth/me -H "authorization: Bearer $TOKEN"
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/auth/me          # 401
curl -s -X POST localhost:8000/auth/sign-in -H 'content-type: application/json' \
  -d '{"account_name":"nobody","password":"x"}'                          # 401 invalid credentials
```

**Expect**: `/auth/me` returns the account's roles with the token, and 401 without it. Unknown
account and wrong password give the same 401 body. API logs show `auth.sign_in` lines with no
password or token.

## 7. Tracing (US6)

Open `http://localhost:16686`, choose service `adlc-api` and find the `/auth/me` request
within 30 seconds. Then run `docker compose -f deploy/compose.yaml --env-file .env stop jaeger`, call
`/auth/me` again, and confirm it still returns 200 and the API logs a WARNING about the
exporter.

## 8. Shared checks (US5)

```bash
make check
```

**Expect**: lint, typecheck, test, migration-check and secret-scan all pass in under 10
minutes. Add a deliberate type error, re-run, and confirm `typecheck` fails by name. CI
(`.github/workflows/ci.yml`) runs the same `make check`.

## 9. Reset (US1)

```bash
make reset         # type the env name when prompted
```

**Expect**: the prompt names the environment, data from step 4 is gone, and the stack comes
back healthy with empty schemas.

## Validation run (2026-11-09, T061)

These results are from a macOS laptop running Docker Desktop. Ports 8000 and 8001 were taken
by other projects there, so `ADLC_API_PORT=8010` was used.

| Step | Result |
| --- | --- |
| 1 Configure | `adlc-account check` → `OK, 1 account (dev)` |
| 2 Start / health / restart | All services healthy about 20 s after `make up`; `/health` ok; a ledger row survived `make down && make up` |
| 3 Missing setting | Exit 2, `ADLC_SESSION_SECRET: missing; …`, no values printed (also covered by `tests/integration/test_startup_config.py`) |
| 4 Ledger immutability | Insert ok; UPDATE (app), DELETE and TRUNCATE (owner) refused with `ledger.ledger_record is append-only`; row unchanged |
| 5 Migration round trip | `make migration-check` passed |
| 6 Sign-in | `/auth/me` returned both roles with a token and 401 without one |
| 7 Tracing | Spans for sign-in and `/auth/me` in Jaeger (query API `/api/v3/traces`); `/health` not traced; no authorization attributes; with Jaeger stopped, requests returned 200 in about 2 ms and a WARNING was logged |
| 8 Shared checks | `make check` passed in about 12 s; a planted type error failed at `==> typecheck`, and a planted token was caught by `secret-scan` |
| 9 Reset | A wrong confirmation changed nothing; the right one emptied the ledger and the stack came back healthy |
