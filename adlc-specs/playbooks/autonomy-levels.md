---
id: PB-T1-02
version: "1.1.0"
title: Autonomy levels
owner_role: adlc_coe
status: active
---
# Autonomy levels

## Purpose

Give every action the agent can take an explicit level of autonomy, so approvers see exactly what
it may do alone and where a person decides.

## Scale

| Level | Name | The agent... |
| --- | --- | --- |
| 0 | Observe | Only reads and reports; takes no action |
| 1 | Suggest | Proposes an action; a person performs it |
| 2 | Act with approval | Prepares the action; a person approves each one before it happens |
| 3 | Act and notify | Acts on reversible actions within limits; a person is told and can undo |
| 4 | Act within bounds | Acts alone within hard limits (amount, scope, rate); exceptions go to a person |
| 5 | Full autonomy | Acts alone without limits (not allowed in this platform) |

## Rules

1. The maximum level per risk tier is a guardrail: low 2, medium 3, high 4. Higher-tier use cases
   may use higher levels only because they carry more controls.
2. Irreversible actions (moving money, changing accounts or contracts, sending messages to
   customers) are at most level 2 and always have `hitl_required: true`.
3. `boundary` states the hard limit in numbers where there is one ("payout up to 200 EUR",
   "one message per claim").
4. Every action with `hitl_required: true` gets a matching row in T2's HITL design, using the same
   action name.

## When to ask

Ask the product owner when it is unclear whether an action is reversible or what its limit is.
