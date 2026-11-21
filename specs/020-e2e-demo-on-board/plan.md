# Implementation Plan: End-to-End Demo on the Board

**Branch**: `020-e2e-demo-on-board` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-e2e-demo-on-board/spec.md` (Gate 1 approved
2026-11-21)

## Summary

The 014 demo, decided on the board. Three parts:

1. **The change request on the board** (016 extended): a fourth kind in the tracker mapping (a
   `Change Request` item under its run's item, decided with Approve change / Reject change in the
   decision field), projected from feature 012's change records, applied through the existing
   change decision, validated by the mapping rules, reconciled like the others; the simulator's
   seed gains the type and the two values.
2. **The driver on the board**: with the sync on, `adlc-demo` acts on the board as each demo person
   through the board port (their tokens) in `--auto`, and tells the presenter the item's address
   and the values in presenter mode; two new steps show D-12 (a person's change reverted with a
   comment) and D-13 (drift corrected by reconciliation); the report lists D-12 and D-13.
3. **The rehearsal**: `make demo-reset` also re-registers the sync's and the people's tokens in the
   freshly seeded simulator (a new `ado-sim token import`) and sets the page passwords; the
   presenter guide describes the board flow and recovery; two auto runs and one presenter run.

## Technical Context

**Language/Version**: Python 3.12 (the platform's and the simulator's uv projects).

**Primary Dependencies**: as today; no new dependency.

**Storage**: no new table (change records are feature 012's `enterprise_record`; board links are
016's with a new object kind).

**Testing**:
- **Unit (test first)**: mapping with the change kind (load, kinds, states, values, platform-written
  fields); classify (a change decision, a run value on a change and a change value on a run);
  desired (the change item: parent, description, state per record state); script validation
  (new actions and expectations, D-12 and D-13); the tokens file (created when missing, mode 600,
  never logged).
- **Spec toolkit**: the schema and V-32 to V-36 with the change kind (valid; missing
  `items.change`; a change state missing).
- **Integration (016 rig with the fake board)**: a change raised for a run appears under the run
  item; approved on the board by the ITSM owner role → recorded as theirs, the run's controls
  re-run, the item Approved; refused for another role (comment, cleared); a second decision
  refused as stale; reconciliation restores a drifted change item.
- **Simulator**: `token import` (registers, refuses short, unknown user, duplicate; never printed);
  the seed's new type and values; the 018 decision-values contract test.
- **Demo**: the driver in board mode over the rig (each action kind becomes a board change by the
  named person; presenter instructions name the item address and values; D-12 and D-13 steps and
  their expectations); the board-mode auto run of the whole script in the integration suite (stub
  agents, the fake board) as 014's auto test does for the inbox; board off: 014's tests unchanged.

**Target Platform / Project Type**: the platform, the simulator and the demo assets.

**Performance Goals**: each board step acted on within one poll interval plus processing (SC-004).

**Constraints**: no board field name, value or terminal in code (the mapping and the script hold
them); the platform imports nothing from the simulator; tokens never in the repository or logs.

**Scale/Scope**: the demo's two use cases.

## Constitution Check

| Article | How this plan complies |
| --- | --- |
| I, II Spec-driven, no values | the change kind, its states and values are mapping data; the steps are script data |
| III Agents build, humans decide | the change approval stays a person's decision, now on the board |
| IV Separation of duties | the change decision keeps feature 012's rights (the ITSM owner role) |
| V Evidence-first | the change item shows the change (summary, risk, window) and what waits for it; the run item links to the evidence |
| VII Interfaces | the driver acts through `BoardAdapter`; the simulator stays behind HTTP |
| IX Test first | mapping, classify, desired, script validation and the token import are test first |
| XI Secure | person tokens in a file outside the repository (mode 600), imported over stdin, never printed |
| XII Simplicity | one decision field; the existing change decision reused; no new table |

**Result: pass.**

## Project Structure

```text
adlc-specs/tracker_mapping.yaml                 items.change, decision values, platform_written
adlc-specs/schema/catalogues/tracker_mapping.schema.json
src/adlc/spec_toolkit/rules/tracker_mapping.py  V-34 for change states
src/adlc/engagement/mapping.py                  KINDS + change accessors
src/adlc/engagement/desired.py                  ChangeSnapshot, the change item
src/adlc/engagement/classify.py                 DECIDE_CHANGE
src/adlc/engagement/inbound.py                  applying it through ChangeService
src/adlc/engagement/wiring.py                   ChangeService in the engagement layer
src/adlc/demo/script.py                         new actions, expectations, moments
src/adlc/demo/board.py                          the board actor (new): people's adapters, items, presenter text
src/adlc/demo/driver.py, __main__.py            board mode
scripts/demo_board.py                           tokens file and imports for demo-reset (new)
Makefile                                        demo-reset imports tokens, sets page passwords
demo/script.yaml, demo/README.md                D-12, D-13 steps; the board flow and recovery
ado_sim/src/ado_sim/cli.py                      token import
ado_sim/seed/demo.yaml, ado_sim/contract/differences.md
tests/unit/engagement/…, tests/integration/engagement/test_change.py, tests/integration/demo/test_board_mode.py,
tests/unit/demo/…, ado_sim/tests/unit/test_cli.py
```

## Complexity Tracking

None.
