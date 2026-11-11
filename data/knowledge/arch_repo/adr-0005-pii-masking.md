---
title: "ADR-0005: mask personal data before model calls"
data_class: internal
synthetic: true
collections: [ADRs]
version: "1.0.0"
---
# ADR-0005: mask personal data before model calls

## Decision

Personal data is masked or pseudonymised before it reaches a model unless the data strategy
approves otherwise; masked data is classified confidential_masked.
