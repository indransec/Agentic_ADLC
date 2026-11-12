---
id: PB-T5-04
version: "1.1.0"
title: Regulatory mapping
owner_role: compliance_officer
status: active
---
# Regulatory mapping

- **regulatory_map** (`regulation, clause, control_id, status`): for each regulation that applies at
  the risk tier (from the policies in grounding and T0's classification), the clauses that bind the
  agent, the control-library id that meets each, and `status` `met`, `partial` or `gap`.
- A `gap` or `partial` row needs a residual risk with an owner.
