---
title: "Reference architecture: tool-using agent with human approval"
data_class: internal
synthetic: true
collections: [reference architectures]
version: "1.0.0"
---
# Reference architecture: tool-using agent with human approval

## Pattern

A single agent with a small set of tools behind the MCP registry, a model gateway with fallback,
and a human approval step for any action that moves money or contacts a customer.

## Components

Channel adapter, agent runtime, tool servers (MCP), model gateway, approval queue, trace and metric
pipeline, kill switch.
