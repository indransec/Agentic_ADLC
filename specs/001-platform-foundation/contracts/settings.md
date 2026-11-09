# Contract: Environment settings

All settings come from the environment. Locally they come from `.env`, which is git-ignored;
the repository holds only `.env.example`. A unit test asserts that `.env.example` lists exactly
the keys below. Duration form: `<int><unit>` with unit `s`, `min`, `h` or `d`.

| Variable | Required | Secret | Form | Default | Used by |
| --- | --- | --- | --- | --- | --- |
| `ADLC_ENV` | yes | no | `dev` \| `demo` | — | all |
| `ADLC_DB_HOST` | yes | no | hostname | — | api, migrate |
| `ADLC_DB_PORT` | no | no | int 1–65535 | `5432` | api, migrate, compose host port |
| `ADLC_DB_NAME` | no | no | identifier | `adlc` | api, migrate, init |
| `ADLC_DB_APP_USER` | no | no | identifier | `adlc_app` | api, init |
| `ADLC_DB_APP_PASSWORD` | yes | yes | ≥ 16 chars | — | api, init |
| `ADLC_DB_OWNER_USER` | no | no | identifier | `adlc_owner` | migrate, init |
| `ADLC_DB_OWNER_PASSWORD` | migrate only | yes | ≥ 16 chars | — | migrate, init |
| `POSTGRES_PASSWORD` | compose only | yes | ≥ 16 chars | — | postgres container superuser |
| `ADLC_DB_CONNECT_TIMEOUT` | no | no | duration | `60s` | api |
| `ADLC_SESSION_SECRET` | yes | yes | ≥ 32 chars | — | api |
| `ADLC_SESSION_TTL` | no | no | duration | `8h` | api |
| `ADLC_ACCOUNTS_FILE` | yes | no | path to readable file | — | api, `adlc-account check` |
| `ADLC_ROLE_CATALOGUE` | no | no | path | `adlc-specs/shared/roles.yaml` | api, `adlc-account check` |
| `ADLC_OTLP_ENDPOINT` | no | no | URL | `http://jaeger:4318` | api |
| `ADLC_API_PORT` | no | no | int | `8000` | compose host port |
| `ADLC_JAEGER_UI_PORT` | no | no | int | `16686` | compose host port |
| `ADLC_LOG_LEVEL` | no | no | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` | api |

## Host and container values

`.env` holds the values that tools run on the host need (`make migrate`, `adlc-account
check`, tests). Containers reach things by different names, so `deploy/compose.yaml` overrides
three settings in the container environment. Nothing else is overridden.

| Variable | In `.env` (host) | Inside `migrate` / `api` containers |
| --- | --- | --- |
| `ADLC_DB_HOST` | `localhost` | `postgres` (service name) |
| `ADLC_DB_PORT` | published host port, e.g. `5432` (also the compose port mapping `${ADLC_DB_PORT}:5432`) | `5432` |
| `ADLC_ACCOUNTS_FILE` | host path of the account file (also the mount source) | `/run/adlc/accounts.yaml` (api only, read-only mount) |

## Failure output (FR-014)

Startup stops with exit code 2 before binding a port and writes to stderr:

```text
adlc: configuration error
  ADLC_SESSION_SECRET: missing; expected at least 32 characters (secret)
  ADLC_DB_PORT: invalid; expected integer 1-65535
```

Values are never echoed, whether or not the setting is secret.
