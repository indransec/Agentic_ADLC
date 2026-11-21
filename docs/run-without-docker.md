# Running the platform without Docker

Everything the platform hosts is Python: the database is one SQLite file, the trace collector is
Arize Phoenix (`deploy/phoenix`), and every platform and pilot service is a Python process. Docker
is optional. This page brings the whole stack up on one machine with nothing but Python tooling.

| Needed | Why |
| --- | --- |
| [uv](https://docs.astral.sh/uv/) 0.10 or later | Installs Python 3.12 and every locked dependency (platform, pilot, Phoenix) |
| `git` (command line) | The pilot bridge keeps a local Git repository per use case (T3–T5 tools) |
| A model provider key | The orchestrator refuses to start without a key for the tiers its model agents use |

uv brings its own Python 3.12 with a recent SQLite (the platform needs 3.42 or later and says so
at startup if it finds an older one).

## Quick start

```bash
make install                       # platform dependencies (uv sync --locked)
cp .env.example .env               # then fill it in, see "Settings" below
make local                         # migrate, register the specs, start every process
```

`make local` runs `make local-setup` (create and migrate the database file, register
`adlc-specs`, install the pilot, Phoenix and ADO simulator projects, and migrate and seed the
simulator's own database), then starts every process of
`deploy/Procfile.local` with [honcho](https://pypi.org/project/honcho/) (a Python Procfile runner,
fetched by `uvx`). Their logs are interleaved in one terminal, prefixed by process name;
**Ctrl-C stops them all**. Data stays in `data/local/` (git-ignored) between runs.

When it is up:

| What | Where |
| --- | --- |
| Web application | `http://127.0.0.1:8501` (`ADLC_UI_PORT`) |
| Platform API | `http://127.0.0.1:8000` (`ADLC_API_PORT`), `GET /health` |
| Traces (Phoenix UI) | `http://127.0.0.1:6006`, project `adlc-platform`; `pilot-triage-<env>` per pilot environment |
| ADO simulator | `http://127.0.0.1:8600` (`ADO_SIM_PORT`): the board page (sign in as a demo user), `GET /health`; data in `data/local/ado_sim/` |
| Orchestrator health | `set -a; source .env; source deploy/local.env; set +a; uv run adlc-orchestrator health` |

## Settings

Settings come from `.env` first, then `deploy/local.env`, which wins. `deploy/local.env` is
committed and holds only the values that differ from compose: localhost URLs, one port per pilot
host and paths under `data/local/`. Your secrets stay in `.env`.

In `.env`, beyond the `REPLACE_ME` values of `.env.example`:

- `ADLC_ACCOUNTS_FILE`: an absolute path to an account file outside the repository
  (`deploy/accounts.example.yaml`; hash passwords with `uv run adlc-account hash`).
- A model provider key, for example `ADLC_OPENAI_API_KEY` with `ADLC_MODEL_PROFILE=dev`, or
  `ADLC_ANTHROPIC_API_KEY` with `ADLC_MODEL_PROFILE=default`.
- `ADLC_API_PORT` and `ADLC_UI_PORT` if 8000 or 8501 is taken.

## Processes and ports

| Process | Command (from `deploy/Procfile.local`) | Port |
| --- | --- | --- |
| `phoenix` | `cd deploy/phoenix && uv run phoenix serve` | 6006 |
| `api` | `uv run adlc-api` | `ADLC_API_PORT` (8000) |
| `orchestrator` | `uv run adlc-orchestrator run` | none (polls every `ADLC_POLL_INTERVAL`) |
| `knowledge` | `uv run adlc-knowledge` | 8020 |
| `tools` | `uv run adlc-tools` | 8030 |
| `bridge` | `uv run adlc-pilot-bridge` | 8040 |
| `ui` | `uv run streamlit run src/adlc/ui/app.py` | `ADLC_UI_PORT` (8501) |
| `pilot-dev` | `cd pilot && uv run pilot-host --env dev --port 8101` | 8101 |
| `pilot-test` | `cd pilot && uv run pilot-host --env test --port 8102` | 8102 |
| `pilot-prodsim` | `cd pilot && uv run pilot-host --env prod-sim --port 8103` | 8103 |
| `pilot-traffic` | `cd pilot && uv run pilot-traffic --port 8200` | 8200 |
| `pilot-lab` | `cd pilot && uv run pilot-lab --port 8300` | 8300 |
| `ado-sim` | `cd ado_sim && uv run ado-sim serve` (`ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db`) | 8600 |
| `board` | `uv run adlc-board run` (off unless `ADLC_BOARD_ENABLED=true`) | 8050 |

Platform processes run from the repository root (they read `adlc-specs/` and `data/` by relative
path); pilot processes run from `pilot/`, its own uv project. The pilot's operator commands take a
full URL where compose uses a service name, for example
`cd pilot && uv run pilot-env http://127.0.0.1:8103 status`.

## Step by step (without honcho)

To run the processes yourself, one terminal each, load the settings in every terminal first:

```bash
set -a; source .env; source deploy/local.env; set +a
```

1. Database and specs, once (and after every pull that changes `db/migrations` or `adlc-specs`):

   ```bash
   make local-setup
   ```

2. Phoenix: `make phoenix` (or the `phoenix` line of `deploy/Procfile.local`).
3. The platform: each of `api`, `orchestrator`, `knowledge`, `tools`, `bridge` and `ui`, with the
   command (and the `OTEL_RESOURCE_ATTRIBUTES` / `ADLC_API_URL` prefix) shown in
   `deploy/Procfile.local`. After step 1 the order does not matter (`make local` starts them all
   at once): each service waits for the database file, and services call each other only when
   work arrives.
4. The pilot: the five `pilot-*` lines of `deploy/Procfile.local`, each with its `PILOT_*`
   settings.
5. The ADO simulator: the `ado-sim` line of `deploy/Procfile.local`. `make local-setup` installed
   it, created `data/local/ado_sim/ado_sim.db` and seeded it. It needs `ADO_SIM_TOKEN_KEY` in
   `.env` (at least 32 characters, e.g. `openssl rand -hex 32`). Issue a token for a client:

   ```bash
   cd ado_sim && ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db uv run ado-sim token issue adlc-platform@adlc.demo
   ```

   For the board page (feature 017), give the demo users a page password once, then open
   `http://127.0.0.1:8600/` and sign in:

   ```bash
   cd ado_sim && ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db uv run ado-sim password set --all
   ```

6. Board engagement (feature 016): the `board` line of `deploy/Procfile.local`. It is off until
   `ADLC_BOARD_ENABLED=true`. To turn it on, issue the service account's token in the simulator
   and put it in `.env` with the flag, and give each account that acts on the board a
   `board_identity` (its simulator user, e.g. `product.owner@adlc.demo`):

   ```bash
   cd ado_sim && ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db uv run ado-sim token issue adlc-platform@adlc.demo
   # .env: ADLC_BOARD_ENABLED=true, ADLC_BOARD_TOKEN=<token>, ADLC_BOARD_ORGANIZATION=adlc-demo,
   #       ADLC_BOARD_PROJECT=Agentic ADLC, ADLC_BOARD_SERVICE_IDENTITY=adlc-platform@adlc.demo
   set -a; source .env; source deploy/local.env; set +a
   uv run adlc-board check-mapping          # -> the tracker mapping fits the board
   ```

   `deploy/local.env` already points it at `http://127.0.0.1:8600`. `uv run adlc-board health`
   shows sync health; `uv run adlc-board reconcile --as <coe account>` corrects drift.

## What differs from compose

- **One host, no network separation.** Compose puts the pilot on its own network, reachable only
  through the pilot bridge and Phoenix. Here every process shares the host, so
  `deploy/pilot-isolation-check.sh` does not apply, and the pilot could reach the platform
  directly. Fine for development and rehearsals; use compose where that separation must hold.
- **Services listen on all interfaces** (`0.0.0.0`), as they do inside containers. On a shared
  network, firewall the ports above or run on a machine of your own.
- **Backups:** stop the processes (or use `sqlite3 data/local/adlc.db ".backup ..."`), then copy
  `data/local/adlc.db` and `data/local/files/` together; Phoenix's traces are in
  `data/local/phoenix/`.
- **Reset:** stop everything, then `rm -rf data/local` and run `make local` again.
