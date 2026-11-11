---
title: "Standard: model gateway"
data_class: internal
synthetic: true
collections: []
version: "1.0.0"
---
# Standard: model gateway

## Rule

Every model call goes through the Halcyon model gateway, with a primary and a fallback model per
tier. Fallback on outages only, never on refusals. Token budgets are enforced per task.
