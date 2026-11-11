---
title: "ADR-0009: human approval for money movements"
data_class: internal
synthetic: true
collections: [ADRs]
version: "1.0.0"
---
# ADR-0009: human approval for money movements

## Decision

No agent moves money or declines a customer without a person approving the action in the approval
queue; timeouts escalate to the team lead.
