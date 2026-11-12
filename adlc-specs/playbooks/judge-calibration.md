---
id: PB-T4-03
version: "1.1.0"
title: Judge calibration
owner_role: qa_eval_lead
status: active
---
# Judge calibration

- The judge is whatever scores the agent's answers. In the MVP it is the harness's deterministic
  scorer (`deterministic-scorer`), comparing answer fields with the dataset's labels.
- Calibration measures how often the judge's verdict agrees with a person's verdict on a labelled
  slice of the dataset (the first rows, whose labels a person reviewed). Report the slice size and
  the agreement rate exactly as the harness returns them.
- When the slice's labels are synthetic stand-ins, say so in the eval store; agreement is then an
  upper bound, not proof.
- Agreement below the parameter's minimum, or a slice smaller than the parameter's minimum, fails
  the calibration controls.
