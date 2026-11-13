---
id: PB-T6-03
version: "1.1.0"
title: Progressive rollout
owner_role: adlc_coe
status: active
---
# Progressive rollout

## Purpose

Release the candidate in stages so a regression reaches as few users as possible, with a success
criterion per stage that T7 checks against measured metrics before going on.

## Stages

The stages come from the use case's tier (`tier.rollout`): high `shadow, canary, full`; medium
`canary, full`; low `full`.

| Stage | Traffic | Soak | Success criterion |
| --- | --- | --- | --- |
| shadow | 0 (mirrored) | 10 min | `routing_accuracy >= <T4 baseline - tolerance>` |
| canary | 10 | 30 min | the shadow criterion, and `pii_outputs == 0` |
| full | 100 | 60 min | the canary criteria |

Soak periods are at the demo time scale. A success criterion names the observability metric, the
operator and the number, so T7 can compare the measured value.

## Rollback

Any stage whose measured metric breaks its criterion is rolled back to the stable package at once
(traffic rollback); the stage result is `fail` and T7 stops.
