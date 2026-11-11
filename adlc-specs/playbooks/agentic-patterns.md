---
id: PB-T2-02
version: "1.1.0"
title: Agentic patterns
owner_role: adlc_coe
status: active
---
# Agentic patterns

## Purpose

Choose the simplest pattern that meets the requirements. More autonomy and more agents mean more
cost, risk and evaluation effort.

## Patterns (from simplest)

| Pattern | Use when | Avoid when |
| --- | --- | --- |
| `single_call` | One model call with retrieved context answers the task | Several systems must be called |
| `rag_assistant` | Answers come from documents; no actions | Actions change systems |
| `tool_using_agent` | One agent calls a few tools in a varying order | Many specialised skills are needed |
| `planner_executor` | Long tasks need a plan, then steps | Tasks are short and predictable |
| `multi_agent` | Distinct specialised roles with clear contracts | One agent with tools is enough |

## GenAI principles (genai_principle column)

- `grounding`: answers cite approved sources.
- `least_privilege`: tools and data limited to what each action needs.
- `human_oversight`: people approve irreversible actions.
- `bounded_execution`: step, token and time limits on every run.
- `observability`: every call is traced and measured.
- `fail_safe`: on doubt, refuse or hand off to a person.

## Steps

1. Start from `single_call` and move down the table only for a stated requirement.
2. Record the choice in `agentic_pattern` with the requirement that forced it, and the principle
   it applies.
