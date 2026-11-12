---
id: PB-T3-03
version: "1.1.0"
title: Prompt versioning
owner_role: engineering_lead
status: active
---
# Prompt versioning

- Every instructions text the agent uses is stored in the prompt registry (`prompt_registry_write`)
  and named in the build manifest by its sha256; the same text always has the same sha256.
- A change to the instructions is a new version: write it, record its sha256, and list the change
  in the change log with the requirement it serves.
- The package hash covers the instructions too, so a changed prompt is always a new candidate.
