---
id: PB-T1-03
version: "1.1.0"
title: Metric catalogue
owner_role: adlc_coe
status: active
---
# Metric catalogue

## Purpose

Name the evaluation and responsible-AI metrics T1 may set thresholds on, so T4 and T8 measure the
same thing. Use these names exactly.

## Evaluation metrics (eval_thresholds)

| Metric | Meaning | Typical threshold |
| --- | --- | --- |
| `task_success_rate` | Share of golden cases resolved correctly | `>= 0.85` (medium), `>= 0.9` (high) |
| `answer_correctness` | Judge score of factual correctness, 0 to 1 | `>= 0.8` |
| `groundedness` | Share of claims supported by retrieved sources | `>= 0.9` |
| `tool_call_accuracy` | Share of tool calls with the right tool and arguments | `>= 0.9` |
| `escalation_precision` | Share of escalations that were needed | `>= 0.7` |
| `latency_p95_s` | 95th percentile response time in seconds | `<= 8` |
| `cost_per_task_usd` | Average model and tool cost per task | `<=` the cost NFR |

## Responsible-AI metrics (rai_thresholds)

| Metric | Meaning | Typical threshold |
| --- | --- | --- |
| `toxicity_rate` | Share of responses flagged toxic | `<= 0.001` |
| `pii_leak_rate` | Share of responses that expose personal data | `<= 0` |
| `jailbreak_success_rate` | Share of adversarial prompts that bypass the rules | `<= 0.01` |
| `fairness_gap` | Largest difference in task success between slices | `<= 0.05` |
| `refusal_appropriateness` | Share of out-of-scope requests refused correctly | `>= 0.95` |

## Steps

1. Pick the metrics the use case's risks need (from T0's risk classification and RAI concerns);
   always include `task_success_rate`, `groundedness` and `pii_leak_rate`.
2. Set thresholds realistic against the baseline; tighten them for higher tiers.
3. Write the operator and a numeric threshold in every row.
