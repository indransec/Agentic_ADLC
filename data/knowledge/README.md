# Synthetic knowledge set (feature 008)

Synthetic enterprise documents for a fictional group, Halcyon (insurance, bank and IT), served by
the knowledge MCP server to the T0–T2 agents. Every document is labelled `synthetic: true`.

## Layout

`<source>/<path>.md`, where `<source>` is an MCP catalogue server (`confluence`, `sharepoint`,
`portfolio`, `jira`, `arch_repo`, `mcp_registry`). A terminal's grounding scope selects documents
by path prefix (`/policies` → `sharepoint/policies/...`) or by collection label (front matter
`collections`).

## Front matter

```yaml
---
title: "Quoted title"         # quote titles: a colon breaks unquoted YAML
data_class: internal          # an id from adlc-specs/shared/data_classes.yaml; required
synthetic: true
collections: [related epics]  # labels matched by grounding scopes that are not paths
version: "1.0.0"
---
```

A document without a valid `data_class` is never served. Sections are Markdown headings; agents
cite a document and section.
