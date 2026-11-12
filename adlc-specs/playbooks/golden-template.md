---
id: PB-T3-02
version: "1.1.0"
title: Golden template
owner_role: adlc_coe
status: active
---
# Golden template

## What it is

The golden template is the approved, fixed implementation of the pilot agent: its code, the
reference data of its mocked tools and the infrastructure definitions of each environment. A use
case changes it only through its **fill points**, which CI validates against the template's rules.

## Fill points

| File | Holds | Rules |
| --- | --- | --- |
| `instructions.md` | The agent's instructions | 1–20,000 characters; no keys or personal data |
| `routing_rules.yaml` | `security_keywords`, `category_keywords` (category → keywords), `category_teams` (category → team), `priority_rules` (`urgency` map, `p1_keywords`) | Categories and teams must exist in the template |
| `tool_bindings.yaml` | `tools`: the mocked tools the agent may call | Only tools the template declares |
| `thresholds.yaml` | `min_confidence_for_auto`, `review_on_multi_service` | Numbers 0–1, true/false |
| `settings.yaml` | `token_budget`, `model_mode`, `model_name` | Budget within the template's limits; mode allowed by the environment |

## How to adapt the example fill

- Keep the example's structure and change values: add keywords the requirements name, set the
  priority rules from the T1 priority and SLA requirements, set the token budget from T2 (never
  above it), raise `min_confidence_for_auto` when T1's autonomy level for assignment requires more
  human review.
- Write the instructions from the T1 functional and behavioural requirements and the T2
  human-in-the-loop design: what the agent decides, what it must never do, when it marks review.
- CI names the failing fill part when a rule is broken; fix that part only.
