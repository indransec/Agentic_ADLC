# Quickstart: End-to-End Demo on the Board (020)

Contracts: [board-and-demo](contracts/board-and-demo.md).

## 1. Checks

```bash
uv run pytest tests/unit tests/integration/engagement tests/integration/demo tests/contract/board tests/scenario
make ado-sim-check
```

## 2. Rehearse (demo environment, Docker)

```bash
# .env: ADLC_ENV=demo, ADLC_BOARD_ENABLED=true, ADLC_BOARD_TOKEN=<40+ chars>,
#       ADO_SIM_DEMO_PASSWORD=<12+ chars>, ADLC_DEMO_BOARD_TOKENS=<path outside the repo>
make demo-reset      # platform, pilot and board; tokens imported; page passwords set
make demo-auto       # every human step on the board; the report shows D-1..D-9, D-12, D-13
make demo-auto       # again, from a reset: SC-001
```

Then once in presenter mode with a browser: the board at `http://localhost:8600`, the console at
`http://localhost:8501` (Journey), following the driver's instructions; check the 1280×720 layout.

## Results

Rehearsed on 2026-11-22 (T017), macOS, Python 3.12, **without Docker** (its daemon was not
running here, and `make demo-reset` wipes the stack's data volumes): the demo script on the board
with real processes. Real: the simulator (`ado-sim serve`, freshly seeded), its tokens registered
with `ado-sim token import` over stdin (the sync's and the 15 demo people's, from a tokens file
created by `adlc.demo.tokens`), the board sync (`adlc-board run`), and the ADO adapter the driver
used as each demo person with that person's own token. The platform ran in the rehearsal script on
014's test harness (the rehearsed replies, the fake pilot), its clock following real time.

| Check | Result |
| --- | --- |
| Tokens | 16 imported over stdin; none in any output |
| The script | 17/17 steps passed in 8.0 minutes (step 10's change approved by the release manager on its Change Request item; step 15's fourth rework escalated; steps 16 and 17 on the board) |
| Moments | D-1 to D-9, D-12 and D-13 each shown, with their runs |
| SC-002 | 31 human board changes by 9 demo people, on use case, run, clarification and change items; 31/31 in the simulator's history as the named person |
| SC-004 | each board step acted on within the sync's 10 s poll (steps of one decision took 20 to 30 s, of two 30 to 50 s) |

The first attempt stopped at step 13 because the rehearsal script gave the driver a different fake
pilot from the platform's (the model swap changed nothing, so no drift opened T9); with one pilot
the run passed. Found while checking (T016) and fixed: since 016, the platform's log handler kept
the stderr it was configured with, so after the board CLI's tests a later CLI's output carried a
logging error (`ledger verify --json`); the handler now writes to the current stderr, and that test
reads the JSON from stdout.

**Still to do with Docker and a browser** (the presenter's rehearsal): `make demo-reset` and
`make demo-auto` twice from a reset on the demo environment (SC-001), one presenter run following
the driver's instructions on the board and the console, the 1280×720 layout, and SC-005 (a
presenter new to the board flow, from the guide alone).
