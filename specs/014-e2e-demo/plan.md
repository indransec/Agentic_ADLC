# Implementation Plan: End-to-End Demo

**Branch**: `014-e2e-demo` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

## Summary

A generic demo driver (`adlc-demo`) runs the SA §21 script from `demo/script.yaml` on the full
stack with rehearsed agent replies (`--live` for models), waiting for the presenter at human steps
(`--auto` takes them) and asking a host wrapper to cause pilot faults (R-01 to R-03).
`make demo-reset` wipes the demo environment (R-04). Offline scenarios cover D-1, D-6, D-8 and the
negatives (R-05); `make resilience` checks restart, duplicate delivery and dead letters on the
running stack (R-06); `adlc-ledger trace` reports traceability (R-07); rehearsal fixes (R-08).

## Technical Context

**Language/Version**: Python 3.12, uv, ruff, mypy strict, pytest.

**Dependencies**: none new.

**Storage**: none new.

**Testing**: unit (script loading and validation, step expectations, trace report on fixed
records, route-fault hook gating); integration (driver in `--auto` over the fake pilot with the
rehearsed replies: completes the script and reports D-1 to D-9); scenario (D-1, D-6, D-8,
negatives). The live checks (`make demo-auto`, `make resilience`) run on the demo stack.

**Settings**: `ADLC_ROUTE_FAULT` (orchestrator; `dev`/`demo` only; unset by default).

**Constraints**: no terminal or use-case names in `src/adlc`; human steps through the service
operations; the reset never runs outside `demo`.

## Constitution Check

| Article | How this plan complies | Status |
| --- | --- | --- |
| I Spec-driven | The demo script and replies are data and demo assets; the driver is generic | Pass |
| III Humans decide | Human steps are people's (or `--auto` acting as named roles through the same operations) | Pass |
| IV Separation of duties | Faults through operator access, never a platform path | Pass |
| V Evidence-first | The demo report and trace link every moment to records | Pass |
| VI Deterministic first | Rehearsed replies make the demo repeatable | Pass |
| XI Secure | Reset and route faults refused outside their environments | Pass |
| XII Simplicity | Reuses the replay gateway, Replayer operations, CLIs | Pass |

**Post-design re-check**: Pass.

## Project Structure

```text
demo/script.yaml  demo/README.md  demo/rehearsed/ (moved from tests/support/acting_scripts.py)  demo/recordings/
src/adlc/demo/__init__.py  driver.py  script.py  __main__.py     # adlc-demo
scripts/demo.py  scripts/resilience.py                          # host wrappers
src/adlc/ledger/trace.py  src/adlc/ledger/cli.py (trace)          # adlc-ledger trace
src/adlc/orchestration/router.py or worker (route-fault hook)
Makefile: demo, demo-auto, demo-reset, resilience, trace
tests/scenario/test_d1_*.py test_d6_*.py test_d8_*.py test_negative_*.py; tests/integration/demo/
```

## Complexity Tracking

| Choice | Why | Simpler alternative rejected because |
| --- | --- | --- |
| Rehearsed reply programs for acting agents | Tool-produced values differ per run | Static recordings fail the evidence controls |
| Host wrapper for faults | Pilot faults are operator-only | A platform fault path would let the platform touch the pilot |
