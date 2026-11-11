---
id: PB-T0-02
version: "1.1.0"
title: Agentic suitability rubric
owner_role: adlc_coe
status: active
---
# Agentic suitability rubric

## Purpose

Decide whether an agent is the right solution, compared with rules, robotic process automation
(RPA) or a classic machine learning model. An agent is justified only where its strengths
(reasoning over unstructured input, multi-step tool use, adapting to variation) are needed.

## Scale (score_1_5)

| Score | Meaning |
| --- | --- |
| 1 | The criterion clearly favours a simpler option |
| 2 | Leans to a simpler option |
| 3 | Neutral: an agent and a simpler option are both viable |
| 4 | Leans to an agent |
| 5 | Clearly needs an agent |

## Criteria (one row each)

1. **Input variability**: are inputs unstructured or highly variable (free text, documents,
   images)? Fixed forms score low.
2. **Reasoning depth**: does the task need judgement across several facts or policies?
3. **Tool orchestration**: does it need several systems or tools in a sequence that varies?
4. **Exception rate**: how often do cases fall outside a fixed flow? Rare exceptions score low.
5. **Tolerance for variation**: can the outcome tolerate non-deterministic wording while staying
   correct? Regulated exact outputs score low.
6. **Human oversight fit**: can a person review the agent's decisions where it matters?
7. **Value at scale**: is the volume high enough to pay for evaluation and operations?

## Steps

1. Score each criterion with a one-sentence rationale citing the intake or a document.
2. Compute the mean. At 3.0 or above an agent is justified; below 3.0 recommend the simpler
   option in the rationale of the lowest criterion.
3. Never inflate a score to pass the control; approvers see the rationale.

## When to ask

Ask the business owner when the volume, exception rate or the decision the agent would take is
unknown.
