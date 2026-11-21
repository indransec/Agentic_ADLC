# Quickstart: Engagement Layer (016)

Validation scenarios that show the feature working end to end. Contracts:
[port](contracts/board-port.md), [mapping](contracts/tracker-mapping.md),
[inbound rules](contracts/inbound-rules.md), [API, commands, settings](contracts/api-cli-settings.md);
data: [data-model](data-model.md).

## 1. Checks

```bash
make check     # includes spec-validate (V-32..V-36), the board contract suite against a simulator
               # it starts itself, the engagement unit and property tests, ado-sim-check
```

## 2. Turn it on without Docker

```bash
make local-setup
cd ado_sim && ADO_SIM_DB_PATH=../data/local/ado_sim/ado_sim.db \
  uv run ado-sim token issue adlc-platform@adlc.demo         # copy the token
# .env: ADLC_BOARD_ENABLED=true, ADLC_BOARD_TOKEN=<token>, ADLC_BOARD_SERVICE_IDENTITY=adlc-platform@adlc.demo,
#       ADLC_BOARD_ORGANIZATION=adlc-demo, ADLC_BOARD_PROJECT=Agentic ADLC,
#       ADLC_BOARD_EVIDENCE_URL=http://127.0.0.1:8501/run?id=
# accounts file: board_identity: <name>@adlc.demo on each demo account
uv run adlc-board check-mapping    # → ok
make local                          # starts `board` with the rest
```

Issue a simulator token for each demo user who will act on the board (`ado-sim token issue
product.owner@adlc.demo`, …).

## 3. Walk it

1. **Register from the board** (US3): as the business owner, create an Epic in `Agentic
   ADLC\Use cases` with a title and description → within 10 s the platform has a new use case
   submitted by that person; the Epic carries its id and sits in the first terminal's column.
2. **See it move** (US1): as the platform runs T0, the Epic's sub-stage changes; a run item
   appears with the evidence link; at sign-off its description lists the decision values.
3. **Decide** (US2): as an approver, set `Pass` with a comment → accepted comment, run closes,
   the Epic moves to the next column, the ledger shows the sign-off by that person with the board
   item as source.
4. **Refusals** (US2, US6, D-12): `Rework` with no root cause → reverted, reason commented;
   `Rework` with `root cause: requirements` in the comment → accepted; a person without the role →
   `not authorised`; drag the Epic to a later column → reverted.
5. **Clarification** (US4): when T2 asks, answer `1. …` on the Task → run continues.
6. **Exception and waiver** (US5): `Exception` with a reason → pending waiver; a different approver
   sets `Approve waiver` → recorded.
7. **Inbox still works** (FR-027): decide the next run in the inbox → the board follows.
8. **Reconcile** (US7, D-13): change an Epic's state directly in the simulator's database or with
   `ADLC_BOARD_ENABLED=false`, then `adlc-board reconcile --as coe.lead` → report lists it; board
   corrected; second run reports nothing.
9. **Outage** (US9): stop the simulator for a minute while deciding in the inbox and editing the
   board; start it → everything delivered once; `adlc-board health` shows watermark age falling.

## 4. Compose

`make up` starts `board` (disabled unless `ADLC_BOARD_ENABLED=true` in `.env`); issue the token
with `docker compose -f deploy/compose.yaml --env-file .env exec ado-sim ado-sim token issue
adlc-platform@adlc.demo`.

## Results

Walked live without Docker on 2026-11-21 (T066), macOS, Python 3.12. Real processes: the ADO
simulator (`ado-sim serve`, scratch database, port 18600) and the board process (`adlc-board run`,
port 18050), talking over HTTP. The platform's database was a scratch copy with the specs
registered; its orchestrator ran in the walking script with stub agents (no model key), as the
integration harness does. People acted on the board through the simulator's API with their own
tokens; accounts carried `board_identity` = the simulator's users. Every step passed.

| Step | Result |
| --- | --- |
| 2. `adlc-board check-mapping` | "the tracker mapping fits the board" |
| 2. `adlc-board run`, `/health` | `{"status": "ok", "gaps": []}` |
| 3.1 register from the board | an Epic by the business owner became UC-0001, submitted by that person, 10.1 s after it was created |
| 3.2 the board follows | the Epic in the T0 column with sub-stage "Awaiting sign-off"; the T0 run item 10.3 s later |
| 3.3 decide from the board | Pass (with the typed values in the Values field) by the business owner; the Epic in the T1 column 19.9 s after the save (SC-001: < 30 s) |
| 3.4 refusals | Rework without a root cause refused with a comment after 10.2 s, the run still awaiting sign-off; an Epic dragged to T5 by another user set back to T1 after 9.7 s |
| 3.7 the inbox still works | a T1 decision in the inbox showed on the board (Epic in the T2 column) 10.2 s later (SC-002: < 15 s) |
| 3.8 reconcile | `adlc-board reconcile --as adlc_coe-person`: exit 0, one difference (a tampered sub-stage) corrected |
| 3.9 outage | the simulator stopped for a poll while T2 passed in the inbox; delivered 6.6 s after it came back |
| health | `adlc-board health`: last poll ok, nothing pending, refusals `missing_input` 1 and `platform_field` 1, 2 reverts |

Clarifications, waivers and escalation completion were not repeated live; they are covered against
the same code by `tests/integration/engagement/` (test_answer, test_waiver_escalation and the
board-versus-inbox lifecycle of SC-007).

Found during the walk: an Epic whose description is shorter than T0's intake prerequisite gives a
run that is blocked; a decision on it is refused with "decide is not allowed in state blocked" and
the board shows the sub-stage "Blocked". That is the platform's rule, not a sync fault.
